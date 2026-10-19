import argparse

from ingest import fixtures, fx, supply_book, weather, worldbank

parser = argparse.ArgumentParser(description="Pull raw extracts into data/raw")
parser.add_argument("--offline", action="store_true",
                    help="generate sample data instead of calling the APIs")
parser.add_argument("--days", type=int, default=365)
args = parser.parse_args()

if args.offline:
    fixtures.run(days=args.days)
else:
    worldbank.run()
    fx.run(days=args.days)
    weather.run(days=args.days)

# The supplier book is simulated against whichever weather extract just landed.
supply_book.run()
