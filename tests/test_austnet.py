"""单元测试：python -m unittest discover -s tests -v。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from austnet import appconfig, netinfo, portal  # noqa: E402

LOGIN_PAGE = """<html>
<script>
authexenable='0';
authloginport=801;
authloginpath='/eportal/?c=ACSetting&a=Login';
authuserfield='DDDDD';
authpassfield='upass';
authsuccess='Dr.COMWebLoginID_3.htm';
authfail='Dr.COMWebLoginID_2.htm';
</script>"""

IPCONFIG = """Windows IP Configuration

   Host Name . . . . . . . . . . . . : Huaiyu

Ethernet adapter 以太网:

   Connection-specific DNS Suffix  . :
   Description . . . . . . . . . . . : Killer E2600 Gigabit Ethernet Controller
   Physical Address. . . . . . . . . : 40-C2-BA-15-9F-48
   DHCP Enabled. . . . . . . . . . . : Yes
   IPv4 Address. . . . . . . . . . . : 192.168.5.73(Preferred)
   Subnet Mask . . . . . . . . . . . : 255.255.255.0
   Default Gateway . . . . . . . . . : 192.168.5.1

Wireless LAN adapter WLAN:

   Description . . . . . . . . . . . : Killer(R) Wi-Fi 6 AX1650i
   Physical Address. . . . . . . . . : A4-F9-33-0F-82-AF
   IPv4 Address. . . . . . . . . . . : 10.1.15.29(Preferred)
   Default Gateway . . . . . . . . . : 10.1.15.254

Tunnel adapter Teredo Tunneling Pseudo-Interface:

   Description . . . . . . . . . . . : Teredo Tunneling Pseudo-Interface
   Physical Address. . . . . . . . . : 00-00-00-00-00-00-00-E0
"""

WLAN_OUTPUT = """系统上有 1 个接口:

    名称                   : WLAN
    描述                   : Killer(R) Wi-Fi 6 AX1650i 160MHz Wireless Network Adapter
    GUID                   : 1a4db9e2-f696-4d84-a5e6-11fedb097d20
    物理地址               : a4:f9:33:0f:82:af
    状态                   : 已连接
    SSID                   : AUST Student
    BSSID                  : 00:11:22:33:44:55
"""


class NetinfoTest(unittest.TestCase):
    def test_split_host_port_defaults_to_80(self):
        self.assertEqual(netinfo.split_host_port("http://10.255.0.19"), ("10.255.0.19", 80))

    def test_split_host_port_keeps_port(self):
        self.assertEqual(
            netinfo.split_host_port("http://10.255.0.19:801/eportal/"), ("10.255.0.19", 801)
        )

    def test_split_line_handles_dotted_labels(self):
        self.assertEqual(
            netinfo.split_line("   描述. . . . . . . . . . . . . . : Killer E2600"),
            ("描述", "Killer E2600"),
        )
        self.assertEqual(
            netinfo.split_line("   IPv4 Address. . . . . . . . . . : 192.168.5.73(Preferred)"),
            ("ipv4address", "192.168.5.73(Preferred)"),
        )

    def test_split_line_ignores_lines_without_separator(self):
        self.assertEqual(netinfo.split_line("Windows IP Configuration"), (None, ""))

    def test_list_adapters_parses_every_adapter(self):
        adapters = netinfo.list_adapters(IPCONFIG)
        self.assertEqual([item.name for item in adapters], ["以太网", "WLAN", "Teredo Tunneling Pseudo-Interface"])
        wired, wireless, tunnel = adapters
        self.assertEqual(wired.ipv4, "192.168.5.73")
        self.assertEqual(wired.gateway, "192.168.5.1")
        self.assertEqual(wired.mac, "40C2BA159F48")
        self.assertEqual(wireless.ipv4, "10.1.15.29")
        self.assertEqual(wireless.mac, "A4F9330F82AF")
        self.assertEqual(tunnel.ipv4, "")

    def test_wlan_interface_reads_ssid_and_state(self):
        info = netinfo.wlan_interface(WLAN_OUTPUT)
        self.assertEqual(info.get("name"), "WLAN")
        self.assertEqual(info.get("ssid"), "AUST Student")
        self.assertEqual(info.get("state"), "已连接")


class PortalClassifyTest(unittest.TestCase):
    def test_success_page_marker(self):
        self.assertTrue(portal.classify('window.location="Dr.COMWebLoginID_3.htm"')[0])

    def test_json_result_one(self):
        ok, _ = portal.classify('dr1003({"result":1,"uid":"2023000000@unicom"})')
        self.assertTrue(ok)

    def test_wrong_password_is_failure(self):
        ok, message = portal.classify('dr1003({"result":0,"msg":"密码错误"})')
        self.assertFalse(ok)
        self.assertIn("密码错误", message)

    def test_login_page_template_is_never_a_verdict(self):
        ok, message = portal.classify(LOGIN_PAGE)
        self.assertFalse(ok)
        self.assertIn("登录页", message)
        self.assertFalse(portal.is_definite_failure(LOGIN_PAGE))

    def test_garbage_response_is_failure(self):
        self.assertFalse(portal.classify("<html>not online</html>")[0])

    def test_redirect_counts_as_accepted(self):
        ok, message = portal.classify("", 302)
        self.assertTrue(ok)
        self.assertIn("302", message)

    def test_redirect_does_not_override_real_error(self):
        ok, message = portal.classify('dr1003({"result":0,"msg":"密码错误"})', 302)
        self.assertFalse(ok)
        self.assertIn("密码错误", message)

    def test_login_page_template_beats_redirect(self):
        self.assertFalse(portal.classify(LOGIN_PAGE, 302)[0])

    def test_definite_failure_only_for_real_errors(self):
        self.assertTrue(portal.is_definite_failure('dr1003({"result":0,"msg":"密码错误"})'))
        self.assertFalse(portal.is_definite_failure('dr1003({"result":1})'))

    def test_failure_page_marker_does_not_stop_other_channels(self):
        """a79 的失败页标志不该挡住 /drcom/login 这条真正管用的通道。"""
        self.assertFalse(portal.is_definite_failure("<html><!--Dr.COMWebLoginID_2.htm--></html>"))
        self.assertFalse(portal.classify("<html><!--Dr.COMWebLoginID_2.htm--></html>")[0])

    def test_extract_json_ignores_trailing_html(self):
        data = portal.extract_json('dr1002({"result":1,"uid":"abc"}) </script></html>')
        self.assertEqual(data.get("result"), 1)
        self.assertEqual(data.get("uid"), "abc")

    def test_extract_json_returns_empty_on_junk(self):
        self.assertEqual(portal.extract_json("<html>404</html>"), {})


class ConfigTest(unittest.TestCase):
    def test_full_account_appends_suffix(self):
        self.assertEqual(appconfig.full_account("2023000000", "@unicom"), "2023000000@unicom")

    def test_full_account_replaces_existing_suffix(self):
        self.assertEqual(appconfig.full_account("2023000000@unicom", "@aust"), "2023000000@aust")

    def test_full_account_without_suffix(self):
        self.assertEqual(appconfig.full_account("2023000000", ""), "2023000000")

    def test_full_account_trims_whitespace(self):
        self.assertEqual(appconfig.full_account("  2023000000 ", "@cmcc"), "2023000000@cmcc")


if __name__ == "__main__":
    unittest.main()
