"""
LSE Stocks Watchlist Configuration.
London Stock Exchange tickers for monitoring.
"""

# FTSE 100 - Large Cap Stocks (verified active)
FTSE_100_TICKERS = [
    # Banks & Finance
    "HSBA.L", "LLOY.L", "STAN.L", "BARC.L", "LGEN.L", "PRU.L", "NG.L", "III.L",
    # Energy
    "BP.L", "SHEL.L", "FRES.L", "GENL.L",
    # Pharma & Healthcare
    "AZN.L", "GSK.L",
    # Consumer
    "ULVR.L", "DGE.L", "RKT.L", "BRBY.L", "ABF.L", "SBRY.L", "TSCO.L", "MKS.L", "JD.L", "SMWH.L",
    # Industrial & Support Services
    "REL.L", "LSEG.L", "EXPN.L", "PSN.L", "BAB.L", "RSW.L", "IAG.L", "RR.L", "EZJ.L", "WIZZ.L", "ICG.L",
    # Mining & Metals
    "RIO.L", "BHP.L", "GLEN.L", "ANTO.L",
    # Telecommunications
    "VOD.L", "FDM.L",
    # Technology
    "AAL.L", "IMB.L", "SGE.L", "AUTO.L",
    # Real Estate & Investment
    "LRE.L", "UTG.L", "BLND.L", "SPX.L", "Land.L", "RESI.L",
    # Utilities
    "UU.L", "SSE.L",
    # Media & Entertainment
    "WPP.L", "ENT.L",
    # Construction & Materials
    "BATS.L",
    # Food & Beverage
    "CCH.L",
]

# FTSE 250 - Mid Cap Stocks (verified active)
FTSE_250_TICKERS = [
    "CRDA.L", "JTC.L", "SYN.L", "BOW.L", "XPS.L", "PLUS.L", "IPX.L", "N91.L", "LIV.L", "TATE.L",
    "KGF.L", "STCM.L", "DOM.L", "GNC.L", "PZC.L", "HIK.L", "PTAL.L", "BME.L", "CTY.L", "THRL.L",
    "ARBB.L", "GLE.L", "MONY.L", "TCAP.L",
]

# ADF Facilities (Facilities by ADF plc) - CONFIRMED: ADF.L
# SEDOL: GB00BNZGNM64
ADF_FACILITIES_TICKER = "ADF.L"

# Combined watchlist - FTSE 100 + FTSE 250 + ADF (no duplicates)
# Use dict.fromkeys() to preserve order and remove duplicates
LSE_WATCHLIST = list(dict.fromkeys(FTSE_100_TICKERS + FTSE_250_TICKERS + [ADF_FACILITIES_TICKER]))

# FTSE list summary
FTSE_100_COUNT = len(FTSE_100_TICKERS)
FTSE_250_COUNT = len(FTSE_250_TICKERS)
TOTAL_WATCHLIST_COUNT = len(LSE_WATCHLIST)