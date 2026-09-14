"""
user_agents.py – Facebook Mobil Uygulama İçi Tarayıcı (FB_IAB / FBAN) User-Agent Havuzu.
Gerçek Android (Samsung, Xiaomi, Pixel vb.) ve iOS (iPhone) Facebook App UA string'leri.
"""

import random

# Facebook Mobile App (In-App Browser) User Agent listesi
USER_AGENTS = [
    # ── Android (Samsung Galaxy Serisi) Facebook App (FB4A) ─────────────────
    "Mozilla/5.0 (Linux; Android 14; SM-S928B Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/126.0.6478.122 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/465.0.0.40.87;]",
    "Mozilla/5.0 (Linux; Android 14; SM-S911B Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/125.0.6422.165 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/462.0.0.47.112;]",
    "Mozilla/5.0 (Linux; Android 13; SM-A546B Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/124.0.6367.179 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/458.0.0.41.111;]",
    "Mozilla/5.0 (Linux; Android 13; SM-G990B Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/123.0.6312.118 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/455.0.0.44.104;]",
    "Mozilla/5.0 (Linux; Android 14; SM-A346B Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/126.0.6478.71 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/464.0.0.44.110;]",
    "Mozilla/5.0 (Linux; Android 13; SM-A145R Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/122.0.6261.119 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/450.0.0.34.109;]",
    "Mozilla/5.0 (Linux; Android 14; SM-S908B Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/125.0.6422.113 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/461.0.0.44.108;]",
    "Mozilla/5.0 (Linux; Android 12; SM-G780G Build/SP1A.210812.016; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/124.0.6367.113 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/456.0.0.39.112;]",
    "Mozilla/5.0 (Linux; Android 14; SM-A536B Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/126.0.6478.50 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/463.0.0.52.105;]",

    # ── Android (Xiaomi / Redmi / POCO Serisi) Facebook App ──────────────────
    "Mozilla/5.0 (Linux; Android 13; 22101316G Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/125.0.6422.165 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/462.0.0.47.112;]",
    "Mozilla/5.0 (Linux; Android 14; 2312DRA50G Build/UKQ1.230917.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/126.0.6478.122 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/465.0.0.40.87;]",
    "Mozilla/5.0 (Linux; Android 13; Redmi Note 12 Pro Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/124.0.6367.113 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/458.0.0.41.111;]",
    "Mozilla/5.0 (Linux; Android 12; 2201116TG Build/SKQ1.211006.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/123.0.6312.80 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/454.0.0.37.106;]",
    "Mozilla/5.0 (Linux; Android 14; POCO F5 Build/UKQ1.230804.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/126.0.6478.71 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/464.0.0.44.110;]",
    "Mozilla/5.0 (Linux; Android 13; 23078PND5G Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/125.0.6422.112 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/460.0.0.38.109;]",

    # ── Android (Google Pixel Serisi) Facebook App ────────────────────────────
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro Build/UD1A.231105.004; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/126.0.6478.122 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/465.0.0.40.87;]",
    "Mozilla/5.0 (Linux; Android 14; Pixel 7a Build/UQ1A.240205.002; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/125.0.6422.165 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/463.0.0.52.105;]",
    "Mozilla/5.0 (Linux; Android 13; Pixel 6 Build/TQ3A.230901.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/124.0.6367.179 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/459.0.0.42.108;]",

    # ── iOS (iPhone) Facebook App (FBAN/FBIOS) ────────────────────────────────
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/21F90 [FBAN/FBIOS;FBDV/iPhone15,3;FBMD/iPhone;FBSN/iOS;FBSV/17.5.1;FBSS/3;FBID/phone;FBLC/tr_TR;FBOP/5]",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/21E236 [FBAN/FBIOS;FBDV/iPhone14,5;FBMD/iPhone;FBSN/iOS;FBSV/17.4.1;FBSS/3;FBID/phone;FBLC/tr_TR;FBOP/5]",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/21F79 [FBAN/FBIOS;FBDV/iPhone15,2;FBMD/iPhone;FBSN/iOS;FBSV/17.5;FBSS/3;FBID/phone;FBLC/tr_TR;FBOP/5]",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_7_8 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/20H343 [FBAN/FBIOS;FBDV/iPhone13,2;FBMD/iPhone;FBSN/iOS;FBSV/16.7.8;FBSS/3;FBID/phone;FBLC/tr_TR;FBOP/5]",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/21D61 [FBAN/FBIOS;FBDV/iPhone14,2;FBMD/iPhone;FBSN/iOS;FBSV/17.3.1;FBSS/3;FBID/phone;FBLC/tr_TR;FBOP/5]",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/21E219 [FBAN/FBIOS;FBDV/iPhone12,1;FBMD/iPhone;FBSN/iOS;FBSV/17.4;FBSS/2;FBID/phone;FBLC/tr_TR;FBOP/5]",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/21F90 [FBAN/FBIOS;FBDV/iPhone16,1;FBMD/iPhone;FBSN/iOS;FBSV/17.5.1;FBSS/3;FBID/phone;FBLC/tr_TR;FBOP/5]",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/20G81 [FBAN/FBIOS;FBDV/iPhone11,8;FBMD/iPhone;FBSN/iOS;FBSV/16.6.1;FBSS/2;FBID/phone;FBLC/tr_TR;FBOP/5]",
]


def random_user_agent() -> str:
    """Havuzdan rastgele bir mobil Facebook App user-agent dondurur."""
    return random.choice(USER_AGENTS)
