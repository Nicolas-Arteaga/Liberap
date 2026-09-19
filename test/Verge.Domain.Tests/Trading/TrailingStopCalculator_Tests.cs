using Shouldly;
using Xunit;

namespace Verge.Trading.Trading;

/// <summary>
/// ROUND 38 — tests de TrailingStopCalculator (Trail-1). Función pura,
/// sin DB/reloj/DI, así que se testean los 15 escenarios del brief
/// directamente contra la matemática, sin infraestructura.
/// </summary>
public class TrailingStopCalculator_Tests
{
    private const decimal Entry = 100m;

    // 1. LONG alcanza +100bp -> SL a breakeven (entry)
    [Fact]
    public void Long_Reaches100bp_MovesSlToBreakeven()
    {
        var r = TrailingStopCalculator.Compute(isLong: true, entryPrice: Entry, favorableExcursionBp: 100m,
            currentSlPrice: 98m, currentTrailLevel: 0);
        r.Changed.ShouldBeTrue();
        r.NewSlPrice.ShouldBe(100m);
        r.NewTrailLevel.ShouldBe(1);
    }

    // 2. LONG alcanza +150bp -> SL asegura +50bp
    [Fact]
    public void Long_Reaches150bp_LocksIn50bp()
    {
        var r = TrailingStopCalculator.Compute(true, Entry, 150m, 98m, currentTrailLevel: 0);
        r.NewSlPrice.ShouldBe(100.5m);
        r.NewTrailLevel.ShouldBe(2);
    }

    // 3. LONG alcanza +200bp -> SL asegura +100bp
    [Fact]
    public void Long_Reaches200bp_LocksIn100bp()
    {
        var r = TrailingStopCalculator.Compute(true, Entry, 200m, 98m, currentTrailLevel: 0);
        r.NewSlPrice.ShouldBe(101m);
        r.NewTrailLevel.ShouldBe(3);
    }

    // 4. LONG alcanza los 3 niveles en llamadas sucesivas (simula 3 ticks reales)
    [Fact]
    public void Long_ReachesAllThreeLevels_Sequentially()
    {
        var r1 = TrailingStopCalculator.Compute(true, Entry, 100m, 98m, 0);
        r1.NewTrailLevel.ShouldBe(1); r1.NewSlPrice.ShouldBe(100m);

        var r2 = TrailingStopCalculator.Compute(true, Entry, 150m, r1.NewSlPrice, r1.NewTrailLevel);
        r2.NewTrailLevel.ShouldBe(2); r2.NewSlPrice.ShouldBe(100.5m);

        var r3 = TrailingStopCalculator.Compute(true, Entry, 200m, r2.NewSlPrice, r2.NewTrailLevel);
        r3.NewTrailLevel.ShouldBe(3); r3.NewSlPrice.ShouldBe(101m);
    }

    // 5-7. SHORT simétrico
    [Fact]
    public void Short_Reaches100bp_MovesSlToBreakeven()
    {
        var r = TrailingStopCalculator.Compute(false, Entry, 100m, currentSlPrice: 102m, currentTrailLevel: 0);
        r.NewSlPrice.ShouldBe(100m);
        r.NewTrailLevel.ShouldBe(1);
    }

    [Fact]
    public void Short_Reaches150bp_LocksIn50bp()
    {
        var r = TrailingStopCalculator.Compute(false, Entry, 150m, 102m, 0);
        r.NewSlPrice.ShouldBe(99.5m);
        r.NewTrailLevel.ShouldBe(2);
    }

    [Fact]
    public void Short_Reaches200bp_LocksIn100bp()
    {
        var r = TrailingStopCalculator.Compute(false, Entry, 200m, 102m, 0);
        r.NewSlPrice.ShouldBe(99m);
        r.NewTrailLevel.ShouldBe(3);
    }

    // 8. Precio retrocede después de +100bp -- el nivel ya aplicado no se deshace
    [Fact]
    public void PriceRetreatsAfter100bp_LevelStaysApplied_NoFurtherChange()
    {
        var r1 = TrailingStopCalculator.Compute(true, Entry, 100m, 98m, 0);
        // el precio retrocede: la excursion FAVORABLE (MaxFavorablePrice) no baja nunca
        // (es un ratchet), asi que favorableExcursionBp sigue siendo 100, no menos.
        var r2 = TrailingStopCalculator.Compute(true, Entry, 100m, r1.NewSlPrice, r1.NewTrailLevel);
        r2.Changed.ShouldBeFalse();
        r2.NewSlPrice.ShouldBe(r1.NewSlPrice);
        r2.NewTrailLevel.ShouldBe(1);
    }

    // 9. Precio retrocede después de +200bp -- el SL asegurado de +100bp no se pierde
    [Fact]
    public void PriceRetreatsAfter200bp_LockedGainSurvives()
    {
        var r1 = TrailingStopCalculator.Compute(true, Entry, 200m, 98m, 0);
        r1.NewSlPrice.ShouldBe(101m);
        // el precio real cae a +20bp, pero MaxFavorablePrice (ratchet) sigue marcando 200bp
        var r2 = TrailingStopCalculator.Compute(true, Entry, 200m, r1.NewSlPrice, r1.NewTrailLevel);
        r2.NewSlPrice.ShouldBe(101m); // se mantiene, no retrocede
    }

    // 10. SL ya mejor que el que calcularia Trail-1 -- no se empeora
    [Fact]
    public void ExistingStopAlreadyBetter_NeverWorsened()
    {
        // estrategia de inyeccion directa (ej. FVG) ya trae un SL mas favorable
        // que el breakeven de Trail-1 (102, mejor que 100 para un LONG)
        var r = TrailingStopCalculator.Compute(true, Entry, 100m, currentSlPrice: 102m, currentTrailLevel: 0);
        r.Changed.ShouldBeFalse("el candidato (100) es peor que el SL existente (102), no debe aplicarse");
        r.NewSlPrice.ShouldBe(102m);
        r.NewTrailLevel.ShouldBe(1, "el nivel se marca alcanzado igual, para no reevaluarlo en cada tick");
    }

    // 11. Multiples ticks despues del mismo umbral -- idempotente
    [Fact]
    public void MultipleTicksAfterSameThreshold_Idempotent()
    {
        var r1 = TrailingStopCalculator.Compute(true, Entry, 100m, 98m, 0);
        var r2 = TrailingStopCalculator.Compute(true, Entry, 100m, r1.NewSlPrice, r1.NewTrailLevel);
        var r3 = TrailingStopCalculator.Compute(true, Entry, 105m, r2.NewSlPrice, r2.NewTrailLevel); // sigue <150
        r2.Changed.ShouldBeFalse();
        r3.Changed.ShouldBeFalse();
        r3.NewSlPrice.ShouldBe(100m);
        r3.NewTrailLevel.ShouldBe(1);
    }

    // 12. Reinicio/reconstruccion del estado -- se persiste en DB (TrailLevelApplied),
    // asi que "reiniciar" es simplemente volver a llamar Compute con el mismo
    // currentTrailLevel leido de la fila -- sin estado en memoria del proceso.
    [Fact]
    public void ProcessRestart_StateReconstructedFromPersistedLevel_NoRegression()
    {
        var afterFirstRun = TrailingStopCalculator.Compute(true, Entry, 150m, 98m, currentTrailLevel: 0);
        // "reinicio": nuevo proceso, sin memoria, pero lee currentTrailLevel=afterFirstRun.NewTrailLevel de la DB
        var afterRestart = TrailingStopCalculator.Compute(true, Entry, 150m, afterFirstRun.NewSlPrice, afterFirstRun.NewTrailLevel);
        afterRestart.Changed.ShouldBeFalse();
        afterRestart.NewSlPrice.ShouldBe(afterFirstRun.NewSlPrice);
    }

    // 13/14: TP o SL alcanzado antes del trail -- responsabilidad del worker, no
    // de esta funcion pura (el worker chequea TP/SL ANTES de llamar a Trail-1,
    // ver SimulationMarkPriceWorker: el bloque de TP/SL hace `continue` y cierra
    // el trade antes de llegar al bloque de trailing). Se documenta la
    // invariante de orden acá con un test de contrato mínimo: Compute no cierra
    // trades ni conoce TpPrice/SlPrice de cierre, solo devuelve un SL candidato.
    [Fact]
    public void ComputeNeverReturnsLevelBelowCurrent_ContractForOrderingWithTpSlCheck()
    {
        // si el trade ya cerro (responsabilidad del worker, fuera de esta clase),
        // esta funcion simplemente no deberia ser invocada -- pero si lo fuera,
        // nunca decrementa el nivel ya persistido.
        var r = TrailingStopCalculator.Compute(true, Entry, 50m /* aun no llego a ningun umbral */, 98m, currentTrailLevel: 2);
        r.NewTrailLevel.ShouldBe(2);
        r.Changed.ShouldBeFalse();
    }

    // 15. Precio salta varios umbrales entre dos actualizaciones (+80bp -> +220bp
    // en un solo tick) -- debe aplicar directamente el nivel MAS ALTO alcanzado.
    [Fact]
    public void PriceJumpsMultipleLevelsInOneTick_AppliesHighestLevelDirectly()
    {
        var r = TrailingStopCalculator.Compute(true, Entry, favorableExcursionBp: 220m, currentSlPrice: 98m, currentTrailLevel: 0);
        r.NewTrailLevel.ShouldBe(3, "debe saltar directo al nivel 3 (+200bp), no quedarse en el 1");
        r.NewSlPrice.ShouldBe(101m);
    }

    [Fact]
    public void PriceJumpsFromLevel1DirectlyToLevel3_SkipsLevel2Explicitly()
    {
        var r1 = TrailingStopCalculator.Compute(true, Entry, 100m, 98m, 0);
        r1.NewTrailLevel.ShouldBe(1);
        var r2 = TrailingStopCalculator.Compute(true, Entry, 250m, r1.NewSlPrice, r1.NewTrailLevel);
        r2.NewTrailLevel.ShouldBe(3);
        r2.NewSlPrice.ShouldBe(101m);
    }

    // Extra: FavorableExcursionBp -- coherencia con el ratchet MaxFavorablePrice
    [Theory]
    [InlineData(true, 100, 102, 200)]   // LONG: (102-100)/100 = 2% = 200bp
    [InlineData(false, 100, 98, 200)]   // SHORT: (100-98)/100 = 2% = 200bp
    public void FavorableExcursionBp_MatchesExpected(bool isLong, decimal entry, decimal maxFav, decimal expectedBp)
    {
        TrailingStopCalculator.FavorableExcursionBp(isLong, entry, maxFav).ShouldBe(expectedBp);
    }
}
