"""Support for Ubiquity mPower devices."""
import re
from datetime import timedelta
import logging
import voluptuous as vol
from homeassistant.components.switch import (SwitchDevice, PLATFORM_SCHEMA)
from homeassistant.const import (
    CONF_HOST, CONF_NAME, CONF_USERNAME, CONF_PASSWORD, CONF_TIMEOUT)
import homeassistant.helpers.config_validation as cv
from homeassistant.util import Throttle

CMD_RELAY = "echo {} > /proc/power/relay{}"

CMD_POWER_STATUS = ("cd /proc/power;grep '' pf* relay* v_rms* "
                    "active_pwr* i_rms* energy_sum*")

DEFAULT_TIMEOUT = 20

DEFAULT_NAME = 'mPower'
DEFAULT_USERNAME = 'ubnt'
DEFAULT_PASSWORD = 'ubnt'

CONF_LABELS = 'labels'

REQUIREMENTS = ['pexpect==4.0.1']
MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=5)

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME): cv.string,
    vol.Optional(CONF_PASSWORD, default=DEFAULT_PASSWORD): cv.string,
    vol.Optional(CONF_LABELS): vol.All(cv.ensure_list, [dict]),
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT):
        vol.All(vol.Coerce(int), vol.Range(min=1, max=600))
})


# pylint: disable=unused-argument
def setup_platform(hass, config, add_devices, discovery_info=None):
    """Configure mPower device."""
    host = config.get(CONF_HOST)
    controllername = config.get(CONF_NAME)
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    timeout = config.get(CONF_TIMEOUT)
    labels = config.get(CONF_LABELS, [])

    controller = MpowerDevice(controllername, host, username, password,
                              timeout)
    controller.update()

    devices = []
    for device_number in controller.states:
        _LOGGER.debug("Adding Ubiquiti mPower outlet %s", str(device_number))
        label = next([label['name'] for label in labels if
                      label['device_number'] == int(device_number)].__iter__(),
                     None)
        devices.append(MpowerOutlet(controller, device_number, label))

    add_devices(devices)


class MpowerOutlet(SwitchDevice):
    """Mpower power outlet."""

    def __init__(self, controller, device_number, label):
        """Create a new power outlet."""
        self._controller = controller
        self._device_number = device_number
        self._label = label
        if self._label:
            self._name = "{}_{}".format(controller.name, label)
        else:
            self._name = "{}_{}".format(controller.name, device_number)

    @property
    def name(self):
        """Return the display name of this relay."""
        return self._name

    @property
    def is_on(self):
        """Return true if power outlet is on."""
        return self._controller.states[self._device_number]['relay'] == '1'

    @property
    def current_power_mwh(self):
        """Return the current power usage in mWh."""
        return float(
            self._controller.states[self._device_number]['active_pwr']) / 1000

    def turn_on(self, **kwargs):
        """Instruct the controller to turn on."""
        self._controller.turn_on(self._device_number)

    def turn_off(self, **kwargs):
        """Instruct the controller to turn off."""
        self._controller.turn_off(self._device_number)

    @property
    def device_state_attributes(self):
        """Return device specific state attributes.

        Power factor, energy sum, voltage, power and current.
        """
        return {
            "power_factor": float(
                self._controller.states[self._device_number]['pf']),
            "energy_sum": float(self._controller.states[self._device_number][
                'energy_sum']),
            "voltage": float(
                self._controller.states[self._device_number]['v_rms']),
            "power": float(self._controller.states[self._device_number][
                'active_pwr']),
            "current": float(
                self._controller.states[self._device_number]['i_rms'])
        }

    def update(self):
        """Trigger update for all power outlets on the parent controller."""
        self._controller.update()


class MpowerDevice(object):
    """mPower device controller."""

    def __init__(self, name, host, username, password, timeout):
        """Create a new controller."""
        self._name = name
        self._host = host
        self._username = username
        self._password = password
        self._timeout = timeout
        self._states = {}
        self._ssh = None

    def _connect(self):
        """Create the SSH connection."""
        from pexpect import pxssh, exceptions
        try:
            if self._ssh is None or not self._ssh.isalive():
                _LOGGER.debug("Create a new SSH connection")
                self._ssh = pxssh.pxssh()
                self._ssh.login(self._host, self._username, self._password,
                                login_timeout=self._timeout)
        except exceptions.EOF:
            _LOGGER.error('Connection refused. Is SSH enabled?')
            self._ssh = None
        except pxssh.ExceptionPxssh as err:
            _LOGGER.error('Unable to connect via SSH: %s', str(err))
            self._ssh = None

    def _switch_state(self, state, device_number):
        """Switch power outlet state."""
        self._connect()
        if self._ssh:
            self._ssh.sendline(CMD_RELAY.format(state, device_number))
            self._ssh.prompt()
            return True
        else:
            _LOGGER.error(
                "Unable to switch power outlet %s state", str(device_number))
            return False

    def turn_on(self, device_number):
        """Turn on power outlet."""
        _LOGGER.debug("Turn on device " + str(device_number))
        switched = self._switch_state(1, device_number)
        if switched:
            self._states[device_number]['relay'] = '1'
        return switched

    def turn_off(self, device_number):
        """Turn off power outlet."""
        _LOGGER.debug("Turn off device " + str(device_number))
        switched = self._switch_state(0, device_number)
        if switched:
            self._states[device_number]['relay'] = '0'
        return switched

    @property
    def states(self):
        """Power outlets states."""
        return self._states

    @property
    def name(self):
        """Controller name."""
        return self._name

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Update device state."""
        _LOGGER.debug("Update device states")
        self._connect()
        if self._ssh:
            self._ssh.sendline(
                CMD_POWER_STATUS)
            self._ssh.prompt()
            power_data = self._ssh.before.split(b'\n')[1:-1]
            regex = r'^([a-z_]+)(\d+):(\d+|\d+\.\d+)$'
            for power_line in power_data:
                clean_result = power_line.decode('utf-8').replace('\r', '')
                match = re.match(regex, clean_result)
                if match and len(match.groups()) == 3:
                    if match.groups()[1] not in self._states:
                        self._states[match.groups()[1]] = {}
                    self._states[match.groups()[1]][match.groups()[0]] = \
                        match.groups()[2]
            _LOGGER.debug(self._states)
        else:
            _LOGGER.error("Unable to get ubiquiti mPower device states")
