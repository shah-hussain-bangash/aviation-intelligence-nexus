"""Operator-only, optional nonbreaking index setup; lookup requests remain read-only."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import time
from services.api.paths import STATE
from services.api.route_history import LOOKUP_SQL, SOURCE

NAME = 'flights_route_history_v1'
COLUMNS = ['source', 'origin', 'destination', 'flight_date']


def ensure_index(database):
    database = Path(database).resolve()
    if not database.is_file():
        raise ValueError('Historical database must already exist')
    started = time.perf_counter()
    with closing(sqlite3.connect(database.as_uri()+'?mode=rw',uri=True,timeout=5)) as connection, connection:
        connection.execute('BEGIN IMMEDIATE')
        names = {row[1] for row in connection.execute("PRAGMA index_list('flights')")}
        before = connection.execute('SELECT COUNT(*) FROM flights').fetchone()[0]
        created = NAME not in names
        if created:
            connection.execute('CREATE INDEX flights_route_history_v1 ON flights(source,origin,destination,flight_date)')
        columns = [row[2] for row in connection.execute("PRAGMA index_info('flights_route_history_v1')")]
        if columns != COLUMNS:
            raise ValueError('Existing index has an unexpected definition; no replacement performed')
        after = connection.execute('SELECT COUNT(*) FROM flights').fetchone()[0]
        if before != after:
            raise RuntimeError('Flight row count changed during setup')
        plan = [row[3] for row in connection.execute('EXPLAIN QUERY PLAN '+LOOKUP_SQL,(SOURCE,'JFK','LAX'))]
        if not any(NAME in row for row in plan):
            raise RuntimeError('Route lookup does not select the expected access path')
    return {'index':NAME,'created':created,'columns':columns,'flight_records':after,
        'query_plan':plan,'elapsed_seconds':round(time.perf_counter()-started,3),
        'scope':'Derived SQLite access path only; no flight/account rows or application migration version changed',
        'production_ready':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,default=STATE/'ain.sqlite3')
    args=parser.parse_args()
    print(json.dumps(ensure_index(args.database),indent=2))
