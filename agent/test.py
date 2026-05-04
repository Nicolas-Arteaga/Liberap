import psycopg2
conn = psycopg2.connect('host=localhost port=5433 dbname=Verge user=postgres password=postgres')
cur = conn.cursor()
cur.execute('SELECT "Symbol", "EntryPrice", "OpenedAt", "ClosedAt" FROM "SimulatedTrades" WHERE "Symbol" = \'SPACEUSDT\'')
rows = cur.fetchall()
for row in rows:
    print(row)
