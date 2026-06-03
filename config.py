from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode


DATABASE_PATH = os.getenv("DATABASE_PATH", "data/real_estate.db")
DOMRIA_LOCAL_CONFIG_PATH = Path("domria_config.json")
DOMRIA_API_BASE_URL = "https://developers.ria.com/dom/search"
DOMRIA_CITIES_API_URL = "https://developers.ria.com/dom/cities"
DOMRIA_DEFAULT_STATE_ID = 18
DOMRIA_DEFAULT_CITY_ID = 18
OLX_DEFAULT_SALE_APARTMENTS_URL = "https://www.olx.ua/uk/nedvizhimost/kvartiry/prodazha-kvartir/lutsk/"
OLX_DEFAULT_RENT_APARTMENTS_URL = "https://www.olx.ua/uk/nedvizhimost/kvartiry/dolgosrochnaya-arenda-kvartir/lutsk/"
OLX_SALE_APARTMENTS_URL = os.getenv("OLX_SALE_APARTMENTS_URL", OLX_DEFAULT_SALE_APARTMENTS_URL)
OLX_RENT_APARTMENTS_URL = os.getenv("OLX_RENT_APARTMENTS_URL", OLX_DEFAULT_RENT_APARTMENTS_URL)

DEAL_TYPES = {
    "sale": "Продаж",
    "rent": "Оренда",
}

PROPERTY_TYPES = {
    "apartments": "Квартири",
    "houses": "Будинки",
    "commercial": "Комерційна нерухомість",
    "land": "Земельні ділянки",
}

ROOMS = {
    "all": "Усі кімнати",
    "1": "1 кімната",
    "2": "2 кімнати",
    "3": "3 кімнати",
    "4_plus": "4+ кімнат",
}

LOCATION_SCOPES = {
    "lutsk": "Луцьк",
    "lutsk_suburbs": "Луцьк + передмістя",
}


@dataclass(frozen=True)
class Category:
    deal_type: str
    property_type: str
    rooms: str
    source: str
    url: str
    display_name: str
    location_scope: str = "lutsk"
    domria_params: dict[str, str | int] | None = None

    @property
    def key(self) -> str:
        return f"{self.deal_type}_{self.property_type}_{self.rooms}"

    @property
    def name(self) -> str:
        return self.display_name


def olx_apartment_url(deal_type: str, rooms: str = "all") -> str:
    action = "prodazha-kvartir" if deal_type == "sale" else "arenda-kvartir"
    url = f"https://www.olx.ua/uk/nedvizhimost/kvartiry/{action}/lutsk/"

    room_filters = {
        "1": "search%5Bfilter_float_number_of_rooms%3Afrom%5D=1&search%5Bfilter_float_number_of_rooms%3Ato%5D=1",
        "2": "search%5Bfilter_float_number_of_rooms%3Afrom%5D=2&search%5Bfilter_float_number_of_rooms%3Ato%5D=2",
        "3": "search%5Bfilter_float_number_of_rooms%3Afrom%5D=3&search%5Bfilter_float_number_of_rooms%3Ato%5D=3",
        "4_plus": "search%5Bfilter_float_number_of_rooms%3Afrom%5D=4",
    }
    if rooms in room_filters:
        return f"{url}?{room_filters[rooms]}"
    return url


def display_name(
    deal_type: str,
    property_type: str,
    rooms: str,
    location_scope: str = "lutsk",
) -> str:
    parts = [DEAL_TYPES[deal_type], PROPERTY_TYPES[property_type].lower()]
    if property_type == "apartments" and rooms != "all":
        parts.append(ROOMS[rooms].lower())
    if location_scope != "lutsk":
        parts.append(LOCATION_SCOPES[location_scope].lower())
    return " · ".join(parts)


def domria_base_params(
    *,
    deal_type: str,
    property_type: str,
    city_id: int = DOMRIA_DEFAULT_CITY_ID,
    state_id: int = DOMRIA_DEFAULT_STATE_ID,
) -> dict[str, str | int]:
    operation_type = "1" if deal_type == "sale" else "3"
    presets = {
        "apartments": {"category": "1", "realty_type": "2"},
        "houses": {"category": "4", "realty_type": "5"},
        "commercial": {"category": "10", "realty_type": "24"},
    }
    return {
        **presets[property_type],
        "operation_type": operation_type,
        "state_id": state_id,
        "city_id": city_id,
    }


def domria_room_params(rooms: str) -> dict[str, str]:
    if rooms == "all":
        return {}
    if rooms == "4_plus":
        return {"characteristic[209][from]": "4"}
    return {
        "characteristic[209][from]": rooms,
        "characteristic[209][to]": rooms,
    }


def domria_url(params: dict[str, str | int]) -> str:
    return f"{DOMRIA_API_BASE_URL}?{urlencode(params)}"


ACTIVE_APARTMENT_ROOMS = ("all", "1", "2", "3")
OPTIONAL_APARTMENT_ROOMS = ("4_plus",)


CATEGORIES = [
    Category(
        deal_type=deal_type,
        property_type="apartments",
        rooms=rooms,
        source="DOM.RIA",
        url=domria_url(
            {
                **domria_base_params(deal_type=deal_type, property_type="apartments"),
                **domria_room_params(rooms),
            }
        ),
        display_name=display_name(deal_type, "apartments", rooms),
        location_scope="lutsk",
        domria_params={
            **domria_base_params(deal_type=deal_type, property_type="apartments"),
            **domria_room_params(rooms),
        },
    )
    for deal_type in ("sale", "rent")
    for rooms in ACTIVE_APARTMENT_ROOMS
]

CATEGORIES.extend(
    [
        Category(
            deal_type="sale",
            property_type="houses",
            rooms="all",
            source="DOM.RIA",
            url=domria_url(domria_base_params(deal_type="sale", property_type="houses")),
            display_name=display_name("sale", "houses", "all"),
            location_scope="lutsk",
            domria_params=domria_base_params(deal_type="sale", property_type="houses"),
        ),
        Category(
            deal_type="sale",
            property_type="commercial",
            rooms="all",
            source="DOM.RIA",
            url=domria_url(domria_base_params(deal_type="sale", property_type="commercial")),
            display_name=display_name("sale", "commercial", "all"),
            location_scope="lutsk",
            domria_params=domria_base_params(deal_type="sale", property_type="commercial"),
        ),
    ]
)

DISABLED_CATEGORIES = [
    Category(
        deal_type=deal_type,
        property_type="apartments",
        rooms=rooms,
        source="DOM.RIA",
        url=domria_url(
            {
                **domria_base_params(deal_type=deal_type, property_type="apartments"),
                **domria_room_params(rooms),
            }
        ),
        display_name=display_name(deal_type, "apartments", rooms),
        location_scope="lutsk",
        domria_params={
            **domria_base_params(deal_type=deal_type, property_type="apartments"),
            **domria_room_params(rooms),
        },
    )
    for deal_type in ("sale", "rent")
    for rooms in OPTIONAL_APARTMENT_ROOMS
]
