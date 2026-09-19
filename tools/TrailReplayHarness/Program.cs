// ROUND 41 — replay del codigo REAL (TrailingStopCalculator.cs, el mismo
// archivo que compila el worker de produccion) contra los trades
// historicos reconstruibles, replicando el ORDEN EXACTO de
// SimulationMarkPriceWorker.UpdateOpenPositionsAsync:
//   1) chequear SL vigente (calculado en el tick/barra ANTERIOR)
//   2) chequear TP vigente
//   3) actualizar MaxFavorablePrice (ratchet)
//   4) TrailingStopCalculator.FavorableExcursionBp + Compute
// Nada de esto se reimplementa en Python -- es el .cs real, compilado.
using System.Globalization;
using Microsoft.Data.Sqlite;
using Npgsql;
using Verge.Trading;

var repoRoot = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", ".."));
var bvPath = Path.Combine(repoRoot, "agent", "data", "binance_vision_clean.db");
var kcPath = Path.Combine(repoRoot, "agent", "data", "klines.db");
const int CapBars = 2880;
const decimal FeePerTrade = 0.12m;

var trades = new List<(string Symbol, int Side, decimal Entry, decimal Sl0, decimal Tp0, DateTime Opened, decimal Amount)>();

await using (var conn = new NpgsqlConnection("Host=localhost;Port=5433;Database=Verge;Username=postgres;Password=postgres"))
{
    await conn.OpenAsync();
    await using var cmd = new NpgsqlCommand(
        @"SELECT ""Symbol"",""Side"",""EntryPrice"",""SlPrice"",""TpPrice"",""OpenedAt"",""Amount""
          FROM ""SimulatedTrades""
          WHERE ""ExitReason"" IN ('tp_hit','sl_hit') AND ""Symbol"" NOT IN ('ONUSDT','BBUSDT')", conn);
    await using var reader = await cmd.ExecuteReaderAsync();
    while (await reader.ReadAsync())
    {
        if (reader.IsDBNull(3) || reader.IsDBNull(4)) continue;
        trades.Add((
            reader.GetString(0), reader.GetInt32(1), reader.GetDecimal(2),
            reader.GetDecimal(3), reader.GetDecimal(4), reader.GetDateTime(5), reader.GetDecimal(6)));
    }
}

Console.WriteLine($"trades tp/sl (sin ONUSDT/BBUSDT): {trades.Count}");

var symbols = trades.Select(t => t.Symbol).Distinct().ToList();
var klineCache = new Dictionary<string, (long[] T, decimal[] O, decimal[] H, decimal[] L, decimal[] C)>();

foreach (var sym in symbols)
{
    var d = LoadKlines(bvPath, sym);
    if (d is null || d.Value.T.Length < 3000)
    {
        var d2 = LoadKlines(kcPath, sym);
        if (d2 is not null && d2.Value.T.Length >= 500) d = d2;
    }
    if (d is not null) klineCache[sym] = d.Value;
}

Console.WriteLine($"simbolos con cobertura: {klineCache.Count}/{symbols.Count}");

int compared = 0, skipped = 0;
decimal totalPnl = 0m;
using var csv = new StreamWriter(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "replay_real_code_output.csv"));
csv.WriteLine("symbol,side,opened,entry,sl0,tp0,exitReason,exitBar,finalLevel,pnl");

foreach (var t in trades)
{
    if (!klineCache.TryGetValue(t.Symbol, out var d)) { skipped++; continue; }
    var openedMs = new DateTimeOffset(DateTime.SpecifyKind(t.Opened, DateTimeKind.Utc)).ToUnixTimeMilliseconds();
    int i = FindBarIndex(d.T, openedMs);
    if (i < 20 || i + 5 >= d.C.Length) { skipped++; continue; }

    bool isLong = t.Side == 0;
    int side = isLong ? 1 : -1;
    decimal size = t.Amount / t.Entry;
    int iStart = i + 1;
    int n = d.C.Length;
    int nBars = Math.Min(CapBars, n - iStart);

    decimal slCur = t.Sl0;
    decimal maxFav = t.Entry;
    int trailLevel = 0;
    string exitReason = "time";
    int exitBar = nBars;
    decimal pnl;

    int k;
    for (k = 0; k < nBars; k++)
    {
        int j = iStart + k;
        decimal hi = d.H[j], lo = d.L[j];

        bool slHit = isLong ? lo <= slCur : hi >= slCur;
        if (slHit) { exitReason = "sl"; exitBar = k; pnl = side * (slCur - t.Entry) * size - FeePerTrade; WriteRow(t, exitReason, exitBar, trailLevel, pnl); totalPnl += pnl; compared++; goto nextTrade; }

        bool tpHit = isLong ? hi >= t.Tp0 : lo <= t.Tp0;
        if (tpHit) { exitReason = "tp"; exitBar = k; pnl = side * (t.Tp0 - t.Entry) * size - FeePerTrade; WriteRow(t, exitReason, exitBar, trailLevel, pnl); totalPnl += pnl; compared++; goto nextTrade; }

        decimal favPx = isLong ? hi : lo;
        maxFav = isLong ? Math.Max(maxFav, favPx) : Math.Min(maxFav, favPx);

        // ---- codigo REAL, compilado desde src/Verge.Domain/Trading/TrailingStopCalculator.cs ----
        var favBp = TrailingStopCalculator.FavorableExcursionBp(isLong, t.Entry, maxFav);
        var result = TrailingStopCalculator.Compute(isLong, t.Entry, favBp, slCur, trailLevel);
        slCur = result.NewSlPrice;
        trailLevel = result.NewTrailLevel;
    }

    {
        int jLast = Math.Min(iStart + nBars - 1, n - 1);
        decimal exitPx = (d.H[jLast] + d.L[jLast]) / 2m;
        pnl = side * (exitPx - t.Entry) * size - FeePerTrade;
        WriteRow(t, "time", nBars, trailLevel, pnl);
        totalPnl += pnl;
        compared++;
    }

    nextTrade: ;
}

Console.WriteLine($"trades comparados: {compared}  descartados: {skipped}");
Console.WriteLine($"PnL total (codigo REAL TrailingStopCalculator.cs): ${totalPnl.ToString("F2", CultureInfo.InvariantCulture)}");

void WriteRow((string Symbol, int Side, decimal Entry, decimal Sl0, decimal Tp0, DateTime Opened, decimal Amount) t, string reason, int bar, int level, decimal pnl)
{
    var ic = CultureInfo.InvariantCulture;
    csv.WriteLine(string.Join(",",
        t.Symbol, t.Side.ToString(ic), t.Opened.ToString("o", ic),
        t.Entry.ToString(ic), t.Sl0.ToString(ic), t.Tp0.ToString(ic),
        reason, bar.ToString(ic), level.ToString(ic), pnl.ToString(ic)));
}

static int FindBarIndex(long[] t, long tsMs)
{
    int lo = 0, hi = t.Length - 1, ans = -1;
    while (lo <= hi)
    {
        int mid = (lo + hi) / 2;
        if (t[mid] <= tsMs) { ans = mid; lo = mid + 1; } else hi = mid - 1;
    }
    return ans;
}

static (long[] T, decimal[] O, decimal[] H, decimal[] L, decimal[] C)? LoadKlines(string dbPath, string symbol)
{
    if (!File.Exists(dbPath)) return null;
    var table = dbPath.EndsWith("binance_vision_clean.db") ? "klines_clean" : "klines";
    using var conn = new SqliteConnection($"Data Source={dbPath};Mode=ReadOnly");
    conn.Open();
    using var cmd = conn.CreateCommand();
    cmd.CommandText = $"SELECT open_time,open,high,low,close FROM {table} WHERE symbol=$sym AND interval='15m' ORDER BY open_time";
    cmd.Parameters.AddWithValue("$sym", symbol);
    using var reader = cmd.ExecuteReader();
    var t = new List<long>(); var o = new List<decimal>(); var h = new List<decimal>(); var l = new List<decimal>(); var c = new List<decimal>();
    while (reader.Read())
    {
        t.Add(reader.GetInt64(0));
        o.Add((decimal)reader.GetDouble(1));
        h.Add((decimal)reader.GetDouble(2));
        l.Add((decimal)reader.GetDouble(3));
        c.Add((decimal)reader.GetDouble(4));
    }
    if (t.Count == 0) return null;
    return (t.ToArray(), o.ToArray(), h.ToArray(), l.ToArray(), c.ToArray());
}
