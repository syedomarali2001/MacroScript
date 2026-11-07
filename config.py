
# ======================================
# FRED Economic Indicators
# ======================================

FRED_SERIES = {

    # 1. Core recession indicators
    "core": {
        "UNRATE": "Unemployment Rate",
        "IC4WSA": "Initial Jobless Claims (4-Week Average)",
        "PAYEMS": "Nonfarm Payroll Employment",
        "INDPRO": "Industrial Production",
        "T10Y3M": "10Y-3M Treasury Yield Spread",
        "NFCI": "Chicago Fed Financial Conditions Index",
    },

    # 2. Additional indicators to investigate
    "optional": {
        "SAHMREALTIME": "Sahm Rule Recession Indicator",
        "PERMIT": "Housing Building Permits",
        "PCEPILFE": "Core PCE Price Index",
    },

    # 3. Historical recession labels
    # Used for backtesting, NOT as a prediction input
    "target": {
        "USREC": "US Recession Indicator",
    },
}
