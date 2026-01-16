CHAMPIONSHIP_TARGETS: dict[str, dict] = {
    "serie_a": {
        "accuracy_target": "72-75%",
        "key_features": ["defensive_strength", "home_advantage_strong"],
        "home_advantage": 0.16,
        "dixon_coles_rho": 0.06,
    },
    "premier_league": {
        "accuracy_target": "70-73%",
        "key_features": ["pace_intensity", "winter_fixture_congestion"],
        "pace_intensity": 0.8,
        "home_advantage": 0.13,
        "dixon_coles_rho": 0.05,
    },
    "la_liga": {
        "accuracy_target": "71-74%",
        "key_features": ["possession_based", "technical_quality"],
        "home_advantage": 0.14,
        "dixon_coles_rho": 0.055,
    },
    "bundesliga": {
        "accuracy_target": "73-76%",
        "key_features": ["high_scoring", "gegenpress_impact"],
        "pace_intensity": 0.6,
        "home_advantage": 0.15,
        "dixon_coles_rho": 0.045,
    },
    "eliteserien": {
        "accuracy_target": "68-71%",
        "key_features": ["weather_impact", "summer_league_timing"],
        "weather_impact": 1.0,
        "home_advantage": 0.12,
        "dixon_coles_rho": 0.08,
    },
}
