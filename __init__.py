"""Support to manage a tracking list."""
from http import HTTPStatus
import logging
import uuid

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import frontend, http, websocket_api
from homeassistant.components.http.data_validator import RequestDataValidator
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_NAME
from homeassistant.core import HomeAssistant, ServiceCall, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.json import load_json, save_json

from .const import (
    DOMAIN,
    EVENT_TRACKING_LIST_UPDATED,
    SERVICE_ADD_ITEM,
    SERVICE_CLEAR_COMPLETED_ITEMS,
    SERVICE_COMPLETE_ALL,
    SERVICE_COMPLETE_ITEM,
    SERVICE_INCOMPLETE_ALL,
    SERVICE_INCOMPLETE_ITEM,
)

ATTR_COMPLETE = "complete"

_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = vol.Schema({DOMAIN: {}}, extra=vol.ALLOW_EXTRA)
ITEM_UPDATE_SCHEMA = vol.Schema({ATTR_COMPLETE: bool, ATTR_NAME: str})
PERSISTENCE = ".tracking_list.json"

SERVICE_ITEM_SCHEMA = vol.Schema({vol.Required(ATTR_NAME): vol.Any(None, cv.string)})
SERVICE_LIST_SCHEMA = vol.Schema({})

WS_TYPE_TRACKING_LIST_ITEMS = "tracking_list/items"
WS_TYPE_TRACKING_LIST_ADD_ITEM = "tracking_list/items/add"
WS_TYPE_TRACKING_LIST_UPDATE_ITEM = "trackingg_list/items/update"
WS_TYPE_TRACKING_LIST_CLEAR_ITEMS = "tracking_list/items/clear"

SCHEMA_WEBSOCKET_ITEMS = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
    {vol.Required("type"): WS_TYPE_TRACKING_LIST_ITEMS}
)

SCHEMA_WEBSOCKET_ADD_ITEM = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
    {vol.Required("type"): WS_TYPE_TRACKING_LIST_ADD_ITEM, vol.Required("name"): str}
)

SCHEMA_WEBSOCKET_UPDATE_ITEM = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
    {
        vol.Required("type"): WS_TYPE_TRACKING_LIST_UPDATE_ITEM,
        vol.Required("item_id"): str,
        vol.Optional("name"): str,
        vol.Optional("complete"): bool,
    }
)

SCHEMA_WEBSOCKET_CLEAR_ITEMS = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
    {vol.Required("type"): WS_TYPE_TRACKING_LIST_CLEAR_ITEMS}
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Initialize the tracking list."""

    if DOMAIN not in config:
        return True

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_IMPORT}
        )
    )

    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up tracking list from config flow."""

    async def add_item_service(call: ServiceCall) -> None:
        """Add an item with `name`."""
        data = hass.data[DOMAIN]
        if (name := call.data.get(ATTR_NAME)) is not None:
            await data.async_add(name)

    async def complete_item_service(call: ServiceCall) -> None:
        """Mark the item provided via `name` as completed."""
        data = hass.data[DOMAIN]
        if (name := call.data.get(ATTR_NAME)) is None:
            return
        try:
            item = [item for item in data.items if item["name"] == name][0]
        except IndexError:
            _LOGGER.error("Removing of item failed: %s cannot be found", name)
        else:
            await data.async_update(item["id"], {"name": name, "complete": True})

    async def incomplete_item_service(call: ServiceCall) -> None:
        """Mark the item provided via `name` as incomplete."""
        data = hass.data[DOMAIN]
        if (name := call.data.get(ATTR_NAME)) is None:
            return
        try:
            item = [item for item in data.items if item["name"] == name][0]
        except IndexError:
            _LOGGER.error("Restoring of item failed: %s cannot be found", name)
        else:
            await data.async_update(item["id"], {"name": name, "complete": False})

    async def complete_all_service(call: ServiceCall) -> None:
        """Mark all items in the list as complete."""
        await data.async_update_list({"complete": True})

    async def incomplete_all_service(call: ServiceCall) -> None:
        """Mark all items in the list as incomplete."""
        await data.async_update_list({"complete": False})

    async def clear_completed_items_service(call: ServiceCall) -> None:
        """Clear all completed items from the list."""
        await data.async_clear_completed()

    data = hass.data[DOMAIN] = TrackingData(hass)
    await data.async_load()

    hass.services.async_register(
        DOMAIN, SERVICE_ADD_ITEM, add_item_service, schema=SERVICE_ITEM_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_COMPLETE_ITEM, complete_item_service, schema=SERVICE_ITEM_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_INCOMPLETE_ITEM,
        incomplete_item_service,
        schema=SERVICE_ITEM_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_COMPLETE_ALL,
        complete_all_service,
        schema=SERVICE_LIST_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_INCOMPLETE_ALL,
        incomplete_all_service,
        schema=SERVICE_LIST_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_COMPLETED_ITEMS,
        clear_completed_items_service,
        schema=SERVICE_LIST_SCHEMA,
    )

    hass.http.register_view(TrackingListView)
    hass.http.register_view(CreateTrackingListItemView)
    hass.http.register_view(UpdateTrackingListItemView)
    hass.http.register_view(ClearCompletedItemsView)

    frontend.async_register_built_in_panel(
        hass, "shopping-list", "shopping_list", "mdi:cart"
    )

    websocket_api.async_register_command(
        hass,
        WS_TYPE_TRACKING_LIST_ITEMS,
        websocket_handle_items,
        SCHEMA_WEBSOCKET_ITEMS,
    )
    websocket_api.async_register_command(
        hass,
        WS_TYPE_TRACKING_LIST_ADD_ITEM,
        websocket_handle_add,
        SCHEMA_WEBSOCKET_ADD_ITEM,
    )
    websocket_api.async_register_command(
        hass,
        WS_TYPE_TRACKING_LIST_UPDATE_ITEM,
        websocket_handle_update,
        SCHEMA_WEBSOCKET_UPDATE_ITEM,
    )
    websocket_api.async_register_command(
        hass,
        WS_TYPE_TRACKING_LIST_CLEAR_ITEMS,
        websocket_handle_clear,
        SCHEMA_WEBSOCKET_CLEAR_ITEMS,
    )

    websocket_api.async_register_command(hass, websocket_handle_reorder)

    return True


class TrackingData:
    """Class to hold tracking list data."""

    def __init__(self, hass):
        """Initialize the tracking list."""
        self.hass = hass
        self.items = []

    async def async_add(self, name, context=None):
        """Add a tracking list item."""
        item = {"name": name, "id": uuid.uuid4().hex, "complete": False}
        self.items.append(item)
        await self.hass.async_add_executor_job(self.save)
        self.hass.bus.async_fire(
            EVENT_TRACKING_LIST_UPDATED,
            {"action": "add", "item": item},
            context=context,
        )
        return item

    async def async_update(self, item_id, info, context=None):
        """Update a shopping list item."""
        item = next((itm for itm in self.items if itm["id"] == item_id), None)

        if item is None:
            raise KeyError

        info = ITEM_UPDATE_SCHEMA(info)
        item.update(info)
        await self.hass.async_add_executor_job(self.save)
        self.hass.bus.async_fire(
            EVENT_TRACKING_LIST_UPDATED,
            {"action": "update", "item": item},
            context=context,
        )
        return item

    async def async_clear_completed(self, context=None):
        """Clear completed items."""
        self.items = [itm for itm in self.items if not itm["complete"]]
        await self.hass.async_add_executor_job(self.save)
        self.hass.bus.async_fire(
            EVENT_TRACKING_LIST_UPDATED,
            {"action": "clear"},
            context=context,
        )

    async def async_update_list(self, info, context=None):
        """Update all items in the list."""
        for item in self.items:
            item.update(info)
        await self.hass.async_add_executor_job(self.save)
        self.hass.bus.async_fire(
            EVENT_TRACKING_LIST_UPDATED,
            {"action": "update_list"},
            context=context,
        )
        return self.items

    @callback
    def async_reorder(self, item_ids, context=None):
        """Reorder items."""
        # The array for sorted items.
        new_items = []
        all_items_mapping = {item["id"]: item for item in self.items}
        # Append items by the order of passed in array.
        for item_id in item_ids:
            if item_id not in all_items_mapping:
                raise KeyError
            new_items.append(all_items_mapping[item_id])
            # Remove the item from mapping after it's appended in the result array.
            del all_items_mapping[item_id]
        # Append the rest of the items
        for key in all_items_mapping:
            # All the unchecked items must be passed in the item_ids array,
            # so all items left in the mapping should be checked items.
            if all_items_mapping[key]["complete"] is False:
                raise vol.Invalid(
                    "The item ids array doesn't contain all the unchecked tracking list items."
                )
            new_items.append(all_items_mapping[key])
        self.items = new_items
        self.hass.async_add_executor_job(self.save)
        self.hass.bus.async_fire(
            EVENT_TRACKING_LIST_UPDATED,
            {"action": "reorder"},
            context=context,
        )

    async def async_load(self):
        """Load items."""

        def load():
            """Load the items synchronously."""
            return load_json(self.hass.config.path(PERSISTENCE), default=[])

        self.items = await self.hass.async_add_executor_job(load)

    def save(self):
        """Save the items."""
        save_json(self.hass.config.path(PERSISTENCE), self.items)


class TrackingListView(http.HomeAssistantView):
    """View to retrieve tracking list content."""

    url = "/api/tracking_list"
    name = "api:tracking_list"

    @callback
    def get(self, request):
        """Retrieve tracking list items."""
        return self.json(request.app["hass"].data[DOMAIN].items)


class UpdateTrackingListItemView(http.HomeAssistantView):
    """View to retrieve tracking list content."""

    url = "/api/tracking_list/item/{item_id}"
    name = "api:tracking_list:item:id"

    async def post(self, request, item_id):
        """Update a tracking list item."""
        data = await request.json()

        try:
            item = await request.app["hass"].data[DOMAIN].async_update(item_id, data)
            return self.json(item)
        except KeyError:
            return self.json_message("Item not found", HTTPStatus.NOT_FOUND)
        except vol.Invalid:
            return self.json_message("Item not found", HTTPStatus.BAD_REQUEST)


class CreateTrackingListItemView(http.HomeAssistantView):
    """View to retrieve tracking list content."""

    url = "/api/tracking_list/item"
    name = "api:tracking_list:item"

    @RequestDataValidator(vol.Schema({vol.Required("name"): str}))
    async def post(self, request, data):
        """Create a new tracking list item."""
        item = await request.app["hass"].data[DOMAIN].async_add(data["name"])
        return self.json(item)


class ClearCompletedItemsView(http.HomeAssistantView):
    """View to retrieve tracking list content."""

    url = "/api/tracking_list/clear_completed"
    name = "api:tracking_list:clear_completed"

    async def post(self, request):
        """Retrieve if API is running."""
        hass = request.app["hass"]
        await hass.data[DOMAIN].async_clear_completed()
        return self.json_message("Cleared completed items.")


@callback
def websocket_handle_items(
    hass: HomeAssistant,
    connection: websocket_api.connection.ActiveConnection,
    msg: dict,
) -> None:
    """Handle get tracking_list items."""
    connection.send_message(
        websocket_api.result_message(msg["id"], hass.data[DOMAIN].items)
    )


@websocket_api.async_response
async def websocket_handle_add(
    hass: HomeAssistant,
    connection: websocket_api.connection.ActiveConnection,
    msg: dict,
) -> None:
    """Handle add item to tracking_list."""
    item = await hass.data[DOMAIN].async_add(msg["name"], connection.context(msg))
    connection.send_message(websocket_api.result_message(msg["id"], item))


@websocket_api.async_response
async def websocket_handle_update(
    hass: HomeAssistant,
    connection: websocket_api.connection.ActiveConnection,
    msg: dict,
) -> None:
    """Handle update tracking_list item."""
    msg_id = msg.pop("id")
    item_id = msg.pop("item_id")
    msg.pop("type")
    data = msg

    try:
        item = await hass.data[DOMAIN].async_update(
            item_id, data, connection.context(msg)
        )
        connection.send_message(websocket_api.result_message(msg_id, item))
    except KeyError:
        connection.send_message(
            websocket_api.error_message(msg_id, "item_not_found", "Item not found")
        )


@websocket_api.async_response
async def websocket_handle_clear(
    hass: HomeAssistant,
    connection: websocket_api.connection.ActiveConnection,
    msg: dict,
) -> None:
    """Handle clearing tracking_list items."""
    await hass.data[DOMAIN].async_clear_completed(connection.context(msg))
    connection.send_message(websocket_api.result_message(msg["id"]))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "tracking_list/items/reorder",
        vol.Required("item_ids"): [str],
    }
)
def websocket_handle_reorder(
    hass: HomeAssistant,
    connection: websocket_api.connection.ActiveConnection,
    msg: dict,
) -> None:
    """Handle reordering tracking_list items."""
    msg_id = msg.pop("id")
    try:
        hass.data[DOMAIN].async_reorder(msg.pop("item_ids"), connection.context(msg))
        connection.send_result(msg_id)
    except KeyError:
        connection.send_error(
            msg_id,
            websocket_api.const.ERR_NOT_FOUND,
            "One or more item id(s) not found.",
        )
    except vol.Invalid as err:
        connection.send_error(msg_id, websocket_api.const.ERR_INVALID_FORMAT, f"{err}")
