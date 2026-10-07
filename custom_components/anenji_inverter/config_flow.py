import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_STICK_IP,
    CONF_STICK_PORT,
    CONF_SERVER_IP,
    CONF_SERVER_PORT,
    CONF_MQTT_HOST,
    CONF_MQTT_PORT,
    CONF_MQTT_USER,
    CONF_MQTT_PASSWORD,
    DEFAULT_STICK_IP,
    DEFAULT_STICK_PORT,
    DEFAULT_SERVER_IP,
    DEFAULT_SERVER_PORT,
    DEFAULT_MQTT_HOST,
    DEFAULT_MQTT_PORT,
)

class AnenjiInverterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Anenji Inverter."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial setup step."""
        errors = {}

        if user_input is not None:
            return self.async_create_entry(
                title=f"Anenji Inverter ({user_input[CONF_STICK_IP]})",
                data=user_input
            )

        # Voluptuous schema defining settings fields
        data_schema = vol.Schema({
            vol.Required(CONF_STICK_IP, default=DEFAULT_STICK_IP): str,
            vol.Required(CONF_STICK_PORT, default=DEFAULT_STICK_PORT): int,
            vol.Required(CONF_SERVER_IP, default=DEFAULT_SERVER_IP): str,
            vol.Required(CONF_SERVER_PORT, default=DEFAULT_SERVER_PORT): int,
            vol.Required(CONF_MQTT_HOST, default=DEFAULT_MQTT_HOST): str,
            vol.Required(CONF_MQTT_PORT, default=DEFAULT_MQTT_PORT): int,
            vol.Optional(CONF_MQTT_USER, default=""): str,
            # Text selector with password mask type renders input as ***
            vol.Optional(CONF_MQTT_PASSWORD, default=""): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return AnenjiInverterOptionsFlowHandler(config_entry)


class AnenjiInverterOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options/re-configuration flow from settings UI."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.data
        data_schema = vol.Schema({
            vol.Required(CONF_STICK_IP, default=options.get(CONF_STICK_IP, DEFAULT_STICK_IP)): str,
            vol.Required(CONF_STICK_PORT, default=options.get(CONF_STICK_PORT, DEFAULT_STICK_PORT)): int,
            vol.Required(CONF_SERVER_IP, default=options.get(CONF_SERVER_IP, DEFAULT_SERVER_IP)): str,
            vol.Required(CONF_SERVER_PORT, default=options.get(CONF_SERVER_PORT, DEFAULT_SERVER_PORT)): int,
            vol.Required(CONF_MQTT_HOST, default=options.get(CONF_MQTT_HOST, DEFAULT_MQTT_HOST)): str,
            vol.Required(CONF_MQTT_PORT, default=options.get(CONF_MQTT_PORT, DEFAULT_MQTT_PORT)): int,
            vol.Optional(CONF_MQTT_USER, default=options.get(CONF_MQTT_USER, "")): str,
            vol.Optional(CONF_MQTT_PASSWORD, default=options.get(CONF_MQTT_PASSWORD, "")): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        })

        return self.async_show_form(step_id="init", data_schema=data_schema)
