from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from derivkit.types import OptionType

_API = "https://api.groww.in/v1"


@dataclass
class Contract:
    trading_symbol: str = ""
    strike: float = 0.0
    type: OptionType = OptionType.CALL
    ltp: float = 0.0
    open_interest: float = 0.0
    volume: float = 0.0
    groww_iv: float = 0.0
    groww_delta: float = 0.0
    groww_gamma: float = 0.0
    groww_theta: float = 0.0
    groww_vega: float = 0.0
    groww_rho: float = 0.0


@dataclass
class Chain:
    source: str = ""
    underlying: str = ""
    exchange: str = "NSE"
    expiry_date: str = ""
    spot: float = 0.0
    rate: float = 0.065
    dividend: float = 0.012
    year_fraction: float = 0.0
    contracts: list[Contract] = field(default_factory=list)


@dataclass
class ClientConfig:
    access_token: str = ""
    api_key: str = ""
    api_secret: str = ""
    totp: str = ""
    exchange: str = "NSE"
    underlying: str = "NIFTY"
    expiry_date: str = ""
    fixture_path: str = ""
    force_fixture: bool = False


def bundled_fixture() -> Path:
    here = Path(__file__).resolve()
    repo = here.parents[2] / "examples" / "data" / "nifty_chain.json"
    pkg = here.parent / "data" / "nifty_chain.json"
    if repo.exists():
        return repo
    return pkg


def from_env() -> ClientConfig:
    cfg = ClientConfig()
    cfg.access_token = os.environ.get("GROWW_ACCESS_TOKEN", "")
    cfg.api_key = os.environ.get("GROWW_API_KEY", "")
    cfg.api_secret = os.environ.get("GROWW_API_SECRET", "")
    cfg.totp = os.environ.get("GROWW_TOTP", "")
    if os.environ.get("GROWW_UNDERLYING"):
        cfg.underlying = os.environ["GROWW_UNDERLYING"]
    if os.environ.get("GROWW_EXPIRY"):
        cfg.expiry_date = os.environ["GROWW_EXPIRY"]
    if os.environ.get("GROWW_FIXTURE"):
        cfg.fixture_path = os.environ["GROWW_FIXTURE"]
    return cfg


def _http(method: str, url: str, token: str = "", body: bytes | None = None) -> str:
    headers = {"Accept": "application/json", "X-API-VERSION": "1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {detail}") from exc


def _parse_leg(node: dict, strike: float, option_type: OptionType) -> Contract:
    c = Contract(strike=strike, type=option_type)
    c.trading_symbol = node.get("trading_symbol", "")
    c.ltp = float(node.get("ltp", 0.0) or 0.0)
    c.open_interest = float(node.get("open_interest", 0.0) or 0.0)
    c.volume = float(node.get("volume", 0.0) or 0.0)
    g = node.get("greeks") or {}
    if isinstance(g, dict):
        c.groww_delta = float(g.get("delta", 0.0) or 0.0)
        c.groww_gamma = float(g.get("gamma", 0.0) or 0.0)
        c.groww_theta = float(g.get("theta", 0.0) or 0.0)
        c.groww_vega = float(g.get("vega", 0.0) or 0.0)
        c.groww_rho = float(g.get("rho", 0.0) or 0.0)
        c.groww_iv = float(g.get("iv", 0.0) or 0.0) / 100.0
    return c


def parse_option_chain(json_text: str) -> Chain:
    root = json.loads(json_text)
    if isinstance(root, dict) and root.get("status") == "FAILURE":
        msg = "Groww API failure"
        if "error" in root:
            msg += f": {root['error']}"
        raise RuntimeError(msg)

    payload = root.get("payload", root) if isinstance(root, dict) else root
    chain = Chain()
    chain.source = root.get("source", "live")
    chain.underlying = root.get("underlying", "NIFTY")
    chain.exchange = root.get("exchange", "NSE")
    chain.expiry_date = root.get("expiry_date", "")
    chain.rate = float(root.get("rate", 0.065))
    chain.dividend = float(root.get("dividend", 0.012))
    chain.year_fraction = float(root.get("year_fraction", 0.0))
    chain.spot = float(payload.get("underlying_ltp", 0.0) or 0.0)
    strikes = payload.get("strikes")
    if not isinstance(strikes, dict):
        raise RuntimeError("option chain JSON is missing payload.strikes")
    for key, node in strikes.items():
        strike = float(key)
        if "CE" in node:
            chain.contracts.append(_parse_leg(node["CE"], strike, OptionType.CALL))
        if "PE" in node:
            chain.contracts.append(_parse_leg(node["PE"], strike, OptionType.PUT))
    chain.contracts.sort(key=lambda c: (c.strike, 0 if c.type is OptionType.CALL else 1))
    return chain


def load_fixture(path: str | Path) -> Chain:
    text = Path(path).read_text(encoding="utf-8")
    chain = parse_option_chain(text)
    chain.source = "fixture"
    return chain


def _extract_token(body: dict) -> str:
    if isinstance(body.get("token"), str):
        return body["token"]
    payload = body.get("payload")
    if isinstance(payload, dict):
        if isinstance(payload.get("token"), str):
            return payload["token"]
        if isinstance(payload.get("access_token"), str):
            return payload["access_token"]
    raise RuntimeError("Groww token response did not contain a token field")


def resolve_access_token(cfg: ClientConfig) -> str:
    if cfg.access_token:
        return cfg.access_token
    if not cfg.api_key:
        return ""
    if cfg.totp:
        body = {"key_type": "totp", "totp": cfg.totp}
    elif cfg.api_secret:
        ts = str(int(time.time()))
        checksum = hashlib.sha256((cfg.api_secret + ts).encode("utf-8")).hexdigest()
        body = {"key_type": "approval", "timestamp": ts, "checksum": checksum}
    else:
        raise RuntimeError(
            "GROWW_API_KEY set but neither GROWW_API_SECRET nor GROWW_TOTP was provided"
        )
    raw = _http(
        "POST",
        f"{_API}/token/api/access",
        token=cfg.api_key,
        body=json.dumps(body).encode("utf-8"),
    )
    return _extract_token(json.loads(raw))


def list_expiries(cfg: ClientConfig, token: str) -> list[str]:
    q = urllib.parse.urlencode(
        {"exchange": cfg.exchange, "underlying_symbol": cfg.underlying}
    )
    body = json.loads(_http("GET", f"{_API}/historical/expiries?{q}", token=token))
    payload = body.get("payload", body)
    out: list[str] = []
    for e in payload.get("expiries") or []:
        if isinstance(e, str):
            out.append(e)
    return out


def nearest_expiry(dates: list[str], today_iso: str) -> str:
    best = ""
    for d in dates:
        if d >= today_iso and (best == "" or d < best):
            best = d
    if best == "" and dates:
        best = max(dates)
    return best


def load_chain(cfg: ClientConfig) -> Chain:
    if cfg.force_fixture or (cfg.fixture_path and not cfg.access_token and not cfg.api_key):
        return load_fixture(cfg.fixture_path)
    token = resolve_access_token(cfg)
    if not token:
        if not cfg.fixture_path:
            raise RuntimeError(
                "No Groww credentials. Set GROWW_ACCESS_TOKEN (or API key + secret), "
                "or pass --fixture."
            )
        return load_fixture(cfg.fixture_path)

    live = cfg
    if not live.expiry_date:
        dates = list_expiries(live, token)
        live.expiry_date = nearest_expiry(dates, datetime.now(timezone.utc).date().isoformat())
        if not live.expiry_date:
            raise RuntimeError(f"Groww returned no expiries for {live.underlying}")

    path = (
        f"{_API}/option-chain/exchange/{urllib.parse.quote(live.exchange)}"
        f"/underlying/{urllib.parse.quote(live.underlying)}"
        f"?expiry_date={urllib.parse.quote(live.expiry_date)}"
    )
    chain = parse_option_chain(_http("GET", path, token=token))
    chain.source = "live"
    chain.underlying = live.underlying
    chain.exchange = live.exchange
    chain.expiry_date = live.expiry_date
    return chain


def years_to_expiry(expiry_iso_date: str) -> float:
    if len(expiry_iso_date) < 10:
        raise ValueError("expiry must be YYYY-MM-DD")
    y, m, d = int(expiry_iso_date[0:4]), int(expiry_iso_date[5:7]), int(expiry_iso_date[8:10])
    expiry = datetime(y, m, d, 10, 0, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    secs = (expiry - now).total_seconds()
    years = secs / (365.25 * 24.0 * 3600.0)
    return max(years, 1.0 / 365.25 / 24.0)
