"""Test the ubiquiti_mpower component."""
import unittest
from unittest import mock
from tests.common import get_test_home_assistant
import logging
from homeassistant.components.switch import ubiquiti_mpower
from pexpect import pxssh, exceptions


def default_component():
    """Return a default component."""
    return {
        'host': '192.168.0.1',
        'name': 'controller'
    }


class MockSshErrorEof():
    """Mock SSH Client with EOF errors."""

    def __init__(self):
        """Create a new ssh client with EOF error."""
        self._host = None

    def login(self, host, username, password,
              login_timeout=60):
        """Mock login."""
        self._host = host
        raise exceptions.EOF("error")


class MockSshError():
    """Mock SSH Client with errors."""

    def __init__(self):
        """Create a new ssh client with error."""
        self._host = None

    def login(self, host, username, password,
              login_timeout=60):
        """Mock login."""
        self._host = host
        raise pxssh.ExceptionPxssh("error")


class MockSsh():
    """Mock SSH Client."""

    def __init__(self):
        """Create a new SSH client."""
        msg = (
            "cd /proc/power;grep '' pf* relay* v_rms* active_pwr*"
            " i_rms* energy_su\r\r\nm*\r\npf1:0.0\r\npf2:0.91073511\r\n"
            "pf3:0.0\r\npf4:0.0\r\npf5:0.0\r\npf6:0.0\r\nrelay1:1\r\n"
            "relay2:1\r\nrelay3:1\r\nrelay4:0\r\nrelay5:1\r\nrelay6:1\r\n"
            "v_rms1:233.138035297\r\nv_rms2:233.23304367\r\n"
            "v_rms3:232.374885559\r\nv_rms4:233.049869537\r\n"
            "v_rms5:232.89024353\r\nv_rms6:233.143782615\r\n"
            "active_pwr1:0.0\r\nactive_pwr2:27.129834473\r\n"
            "active_pwr3:0.0\r\nactive_pwr4:0.0\r\nactive_pwr5:0.0\r\n"
            "active_pwr6:0.0\r\ni_rms1:0.0\r\ni_rms2:0.127721786\r\n"
            "i_rms3:0.0\r\ni_rms4:0.0\r\ni_rms5:0.0\r\ni_rms6:0.0\r\n"
            "energy_sum1:54.375\r\nenergy_sum2:124.6875\r\nenergy_sum3:0.0\r\n"
            "energy_sum4:23.4375\r\nenergy_sum5:0.0\r\nenergy_sum6:0.0\r\n"
        )
        self.before = str.encode(msg)

    def login(self, host, username, password,
              login_timeout=60):
        """Mock login."""
        pass

    def isalive(self):
        """Mock isalive."""
        return False

    def sendline(self, command):
        """Mock sendline."""
        pass

    def prompt(self):
        """Mock prompt."""
        pass


class TestUbiquitimPowerDevice(unittest.TestCase):
    """Ubiquiti mPower device test class."""

    def setUp(self):  # pylint: disable=invalid-name
        """Setup things to be run when tests are started."""
        self.hass = get_test_home_assistant()
        logging.disable(logging.CRITICAL)

    def tearDown(self):  # pylint: disable=invalid-name
        """Stop everything that was started."""
        logging.disable(logging.NOTSET)
        self.hass.stop()

    @mock.patch('pexpect.pxssh.pxssh', side_effect=MockSsh)
    def test_ensure_setup_config(self, mpower_device_update):
        """Test setup OK."""
        ubiquiti_mpower.setup_platform(self.hass, default_component(),
                                       mock.MagicMock())
        self.assertEqual(mpower_device_update.call_count, 1)

    @mock.patch('pexpect.pxssh.pxssh', side_effect=MockSsh)
    def test_controller(self, mpower_device_update):
        """Test controller."""
        device = ubiquiti_mpower.MpowerDevice('name', 'host', 'username',
                                              'password', 60)
        device.update()
        self.assertEqual(mpower_device_update.call_count, 1)
        self.assertEqual(device.name, 'name')
        self.assertEqual(device.states['1']['energy_sum'], str(54.375))

    @mock.patch('pexpect.pxssh.pxssh', side_effect=MockSsh)
    def test_power_outlet(self, mpower_device):
        """Test power outlet."""
        device = ubiquiti_mpower.MpowerDevice('name', 'host', 'username',
                                              'password', 60)
        device.update()
        self.assertEqual(mpower_device.call_count, 1)
        p_outlet = ubiquiti_mpower.MpowerOutlet(device, '2', 'tv')
        p_outlet.update()
        self.assertEqual(p_outlet.name, 'name_tv')
        self.assertEqual(p_outlet.device_state_attributes['power_factor'],
                         0.91073511)
        self.assertTrue(p_outlet.is_on)
        self.assertEqual(p_outlet.current_power_mwh, 0.027129834473)

    @mock.patch('pexpect.pxssh.pxssh', side_effect=MockSsh)
    def test_power_outlet_turn_on(self, mpower_device):
        """Test power outlet turn on."""
        device = ubiquiti_mpower.MpowerDevice('name', 'host', 'username',
                                              'password', 60)
        device.update()
        self.assertEqual(mpower_device.call_count, 1)
        p_outlet = ubiquiti_mpower.MpowerOutlet(device, '4', 'tv')
        self.assertFalse(p_outlet.is_on)
        p_outlet.turn_on()
        self.assertTrue(p_outlet.is_on)

    @mock.patch('pexpect.pxssh.pxssh', side_effect=MockSsh)
    def test_power_outlet_turn_off(self, mpower_device):
        """Test power outlet turn off."""
        device = ubiquiti_mpower.MpowerDevice('name', 'host', 'username',
                                              'password', 60)
        device.update()
        self.assertEqual(mpower_device.call_count, 1)
        p_outlet = ubiquiti_mpower.MpowerOutlet(device, '1', 'tv')
        self.assertTrue(p_outlet.is_on)
        p_outlet.turn_off()
        self.assertFalse(p_outlet.is_on)

    @mock.patch('pexpect.pxssh.pxssh', side_effect=MockSshErrorEof)
    def test_error_ssh_eof(self, mpower_device):
        """Test device with SSH OEF errors."""
        device = ubiquiti_mpower.MpowerDevice('name', 'host', 'username',
                                              'password', 60)
        device.update()
        self.assertEqual(mpower_device.call_count, 1)
        self.assertEqual(device.states, {})
        p_outlet = ubiquiti_mpower.MpowerOutlet(device, '1', 'tv')
        p_outlet.turn_off()
        p_outlet.turn_on()

    @mock.patch('pexpect.pxssh.pxssh', side_effect=MockSshError)
    def test_error_ssh(self, mpower_device):
        """Test device with SSH errors."""
        device = ubiquiti_mpower.MpowerDevice('name', 'host', 'username',
                                              'password', 60)
        device.update()
        self.assertEqual(mpower_device.call_count, 1)
        self.assertEqual(device.states, {})
        p_outlet = ubiquiti_mpower.MpowerOutlet(device, '1', 'tv')
        p_outlet.turn_off()
        p_outlet.turn_on()
