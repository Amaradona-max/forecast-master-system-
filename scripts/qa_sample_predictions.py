import json

from ml_engine.ensemble_predictor.service import EnsemblePredictorService


LEAGUES = ["serie_a", "premier_league", "la_liga", "bundesliga"]

SAMPLES = {
    "serie_a": [("Inter", "Milan"), ("Juventus", "Roma")],
    "premier_league": [("Arsenal", "Chelsea"), ("Liverpool", "Man City")],
    "la_liga": [("Real Madrid", "Barcelona"), ("Sevilla", "Valencia")],
    "bundesliga": [("Bayern Munich", "Dortmund"), ("Leverkusen", "Leipzig")],
}


def main() -> None:
    svc = EnsemblePredictorService()
    for league in LEAGUES:
        print("\n" + "=" * 80)
        print("LEAGUE:", league)
        for home, away in SAMPLES[league]:
            out = svc.predict(championship=league, home_team=home, away_team=away, status="PREMATCH", context={"matchday": 12})
            print(f"\n{home} vs {away}")
            print("probabilities:", out.get("probabilities"))
            print("ranges:", out.get("ranges"))
            print("confidence:", out.get("confidence"))
            explain = out.get("explain", {})
            if isinstance(explain, dict):
                comps = explain.get("ensemble_components", {})
                if comps:
                    print("components:", json.dumps(comps, indent=2)[:1000])


if __name__ == "__main__":
    main()

