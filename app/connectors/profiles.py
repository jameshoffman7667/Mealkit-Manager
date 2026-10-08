"""Where each service's pages are and how to find things on them.

These values are starting points. They have NOT been checked against the live sites and a site redesign
can break them. Fix them without rebuilding the image by putting overrides in DATA_DIR/connectors.json:
  {"hellofresh": {"deliveries_path": "/my-account/deliveries", "card_sel": "[data-testid=card]"}}
"""
import json
import os
from dataclasses import dataclass, fields, replace

from .. import config


@dataclass(frozen=True)
class SiteProfile:
    service_id: str
    base_url: str
    login_path: str = "/login"
    deliveries_path: str = "/my-account/deliveries"
    plan_path: str = "/my-account/plan"
    email_sel: str = 'input[type="email"], input[name="email"], input[id="email"]'
    password_sel: str = 'input[type="password"]'
    submit_sel: str = 'button[type="submit"]'
    card_sel: str = ("[data-testid='delivery-card'], [class*='DeliveryCard'], [class*='delivery-card'], "
                     "[class*='deliveryCard']")
    verified: bool = False


PROFILES = {
    "hellofresh": SiteProfile("hellofresh", os.environ.get("HELLOFRESH_URL", "https://www.hellofresh.ca")),
    "chefsplate": SiteProfile("chefsplate", os.environ.get("CHEFSPLATE_URL", "https://www.chefsplate.com")),
    "goodfood": SiteProfile("goodfood", os.environ.get("GOODFOOD_URL", "https://www.makegoodfood.ca"),
                            login_path="/en/login", deliveries_path="/en/account/deliveries",
                            plan_path="/en/account/plan"),
}


def get_profile(service_id: str) -> SiteProfile:
    if service_id not in PROFILES:
        raise KeyError(f"No connector for service {service_id}")
    prof = PROFILES[service_id]
    path = config.data_dir() / "connectors.json"
    if path.exists():
        try:
            over = json.loads(path.read_text()).get(service_id, {})
            names = {f.name for f in fields(SiteProfile)} - {"service_id"}
            prof = replace(prof, **{k: v for k, v in over.items() if k in names})
        except (OSError, ValueError, TypeError):
            pass
    return prof
