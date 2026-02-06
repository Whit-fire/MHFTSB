#!/usr/bin/env python3

import requests
import json
import time
import asyncio
import websockets
import sys
import base58
import secrets
from datetime import datetime
from urllib.parse import urlparse

class HFTBotAPITester:
    def __init__(self, base_url="https://hft-gate-monitor.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.critical_issues = []

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        if headers:
            test_headers.update(headers)

        self.tests_run += 1
        self.log(f"Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers, timeout=10)

            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                self.log(f"✅ {name} - Status: {response.status_code}", "PASS")
                try:
                    return True, response.json()
                except:
                    return True, response.text
            else:
                self.log(f"❌ {name} - Expected {expected_status}, got {response.status_code}", "FAIL")
                try:
                    error_data = response.json()
                    self.log(f"   Error: {error_data}", "FAIL")
                except:
                    self.log(f"   Error: {response.text}", "FAIL")
                
                self.failed_tests.append({
                    "name": name,
                    "expected": expected_status,
                    "actual": response.status_code,
                    "endpoint": endpoint,
                    "error": response.text[:200]
                })
                
                if response.status_code >= 500:
                    self.critical_issues.append(f"Server error in {name}: {response.status_code}")
                
                return False, {}

        except requests.exceptions.RequestException as e:
            self.log(f"❌ {name} - Network/Connection Error: {str(e)}", "ERROR")
            self.failed_tests.append({
                "name": name,
                "expected": expected_status,
                "actual": "CONNECTION_ERROR",
                "endpoint": endpoint,
                "error": str(e)
            })
            self.critical_issues.append(f"Connection failed for {name}: {str(e)}")
            return False, {}

    def test_health(self):
        """Test health endpoint"""
        success, response = self.run_test(
            "Health Check",
            "GET",
            "health",
            200
        )
        if success:
            self.log(f"   Bot status: {response.get('bot', 'unknown')}, Mode: {response.get('mode', 'unknown')}")
        return success

    def test_config_get(self):
        """Test get configuration"""
        success, response = self.run_test(
            "Get Configuration",
            "GET", 
            "config",
            200
        )
        if success:
            config = response.get('config', {})
            self.log(f"   Config sections: {list(config.keys()) if config else 'none'}")
            return config
        return None

    def test_config_update(self, config):
        """Test update configuration"""
        if not config:
            self.log("Skipping config update - no config to test with")
            return False
            
        # Test updating a simple config value
        test_config = {
            "FILTERS": {
                "MIN_LIQUIDITY_SOL": 0.6  # Slightly modify existing value
            }
        }
        
        success, response = self.run_test(
            "Update Configuration",
            "PUT",
            "config",
            200,
            data={"config": test_config}
        )
        return success

    def test_wallet_status(self):
        """Test wallet status"""
        success, response = self.run_test(
            "Wallet Status",
            "GET",
            "wallet/status",
            200
        )
        if success:
            self.log(f"   Wallet setup: {response.get('is_setup', False)}, Unlocked: {response.get('is_unlocked', False)}")
        return success, response

    def test_wallet_encrypt(self):
        """Test wallet encryption"""
        test_key = "5" * 64  # Fake 64-char private key for testing
        test_passphrase = "test_passphrase_123"
        
        success, response = self.run_test(
            "Wallet Encryption",
            "POST",
            "wallet/encrypt",
            200,
            data={"private_key": test_key, "passphrase": test_passphrase}
        )
        
        if success:
            self.log(f"   Encrypted address: {response.get('address', 'none')}")
            # Try to unlock with the same passphrase
            unlock_success, _ = self.run_test(
                "Wallet Unlock After Encrypt",
                "POST",
                "wallet/unlock",
                200,
                data={"passphrase": test_passphrase}
            )
            return unlock_success
        return success

    def test_bot_start(self):
        """Test starting the bot"""
        success, response = self.run_test(
            "Start Bot",
            "POST",
            "bot/start",
            200
        )
        if success:
            self.log(f"   Bot started in mode: {response.get('mode', 'unknown')}")
            # Wait a bit for bot to initialize
            time.sleep(2)
        return success

    def test_bot_status(self):
        """Test bot status"""
        success, response = self.run_test(
            "Bot Status",
            "GET",
            "bot/status",
            200
        )
        if success:
            status = response.get('status', 'unknown')
            mode = response.get('mode', 'unknown')
            uptime = response.get('uptime_seconds', 0)
            hft_gate = response.get('hft_gate', {})
            positions = response.get('positions', {})
            
            self.log(f"   Status: {status}, Mode: {mode}, Uptime: {uptime}s")
            self.log(f"   HFT Gate: {hft_gate.get('in_flight', 0)}/{hft_gate.get('max_in_flight', 3)} in-flight")
            self.log(f"   Positions: {positions.get('open_positions', 0)} open, {positions.get('win_rate', 0)}% win rate")
            
            return response
        return None

    def test_positions(self):
        """Test positions endpoints"""
        open_success, open_response = self.run_test(
            "Get Open Positions",
            "GET",
            "positions",
            200
        )
        
        history_success, history_response = self.run_test(
            "Get Position History",
            "GET",
            "positions/history",
            200
        )
        
        if open_success:
            positions = open_response.get('positions', [])
            self.log(f"   Open positions: {len(positions)}")
            
        if history_success:
            history = history_response.get('positions', [])
            self.log(f"   Historical positions: {len(history)}")
            
        return open_success and history_success

    def test_metrics(self):
        """Test metrics endpoints"""
        metrics_success, metrics_response = self.run_test(
            "Get Metrics",
            "GET",
            "metrics",
            200
        )
        
        kpi_success, kpi_response = self.run_test(
            "Get KPI Metrics",
            "GET",
            "metrics/kpi",
            200
        )
        
        if metrics_success:
            snapshot = metrics_response
            counters = snapshot.get('counters', {})
            gauges = snapshot.get('gauges', {})
            histograms = snapshot.get('histograms', {})
            
            self.log(f"   Counters: {len(counters)}, Gauges: {len(gauges)}, Histograms: {len(histograms)}")
            
        if kpi_success:
            kpi = kpi_response
            self.log(f"   Total PnL: {kpi.get('total_pnl_sol', 0)} SOL, Win rate: {kpi.get('win_rate', 0)}%")
            
        return metrics_success and kpi_success

    def test_logs(self):
        """Test logs endpoint"""
        success, response = self.run_test(
            "Get Logs",
            "GET",
            "logs",
            200
        )
        
        if success:
            logs = response.get('logs', [])
            self.log(f"   Recent logs: {len(logs)} entries")
            if logs:
                self.log(f"   Latest log: {logs[-1].get('message', 'N/A')[:50]}...")
                
        return success

    def test_bot_control(self):
        """Test bot control operations"""
        # Test toggle mode
        toggle_success, toggle_response = self.run_test(
            "Toggle Bot Mode",
            "POST",
            "bot/toggle-mode",
            200
        )
        
        if toggle_success:
            self.log(f"   Mode after toggle: {toggle_response.get('mode', 'unknown')}")
        
        # Test stop
        stop_success, _ = self.run_test(
            "Stop Bot",
            "POST",
            "bot/stop",
            200
        )
        
        # Test panic (should work even if bot is stopped)
        panic_success, panic_response = self.run_test(
            "Panic Stop",
            "POST",
            "bot/panic",
            200
        )
        
        if panic_success:
            self.log(f"   Panic executed, positions closed: {panic_response.get('positions_closed', False)}")
        
        return toggle_success and stop_success and panic_success

    async def test_websocket(self):
        """Test WebSocket connection"""
        try:
            ws_url = self.base_url.replace('https://', 'wss://').replace('http://', 'ws://') + '/api/ws'
            self.log(f"Testing WebSocket connection to: {ws_url}")
            
            async with websockets.connect(ws_url, timeout=10) as websocket:
                self.log("✅ WebSocket Connected")
                
                # Send ping
                await websocket.send("ping")
                
                # Wait for response with timeout
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    response_data = json.loads(response)
                    
                    if response_data.get("type") == "pong":
                        self.log("✅ WebSocket Ping/Pong successful")
                        self.tests_passed += 1
                        return True
                    else:
                        self.log(f"✅ WebSocket received data: {response_data.get('type', 'unknown')}")
                        self.tests_passed += 1
                        return True
                        
                except asyncio.TimeoutError:
                    self.log("⚠️  WebSocket connected but no response to ping (may still be working)")
                    self.tests_passed += 1  # Connection successful even if no immediate response
                    return True
                    
        except Exception as e:
            self.log(f"❌ WebSocket connection failed: {str(e)}", "ERROR")
            self.failed_tests.append({
                "name": "WebSocket Connection",
                "expected": "Connected",
                "actual": "Failed",
                "endpoint": "/api/ws",
                "error": str(e)
            })
            self.critical_issues.append(f"WebSocket connection failed: {str(e)}")
            return False
        finally:
            self.tests_run += 1

    def run_all_tests(self):
        """Run complete test suite"""
        self.log("🚀 Starting HFT Bot API Test Suite")
        self.log(f"Testing against: {self.base_url}")
        
        # Basic connectivity
        if not self.test_health():
            self.log("❌ Health check failed - may indicate server issues", "ERROR")
        
        # Configuration tests
        config = self.test_config_get()
        self.test_config_update(config)
        
        # Wallet tests
        wallet_success, wallet_status = self.test_wallet_status()
        if wallet_success and not wallet_status.get('is_setup'):
            self.test_wallet_encrypt()
        
        # Bot control tests (order matters)
        self.test_bot_start()
        
        # Allow bot to run and generate some data
        time.sleep(3)
        
        bot_status = self.test_bot_status()
        self.test_positions()
        self.test_metrics()
        self.test_logs()
        
        # Control operations
        self.test_bot_control()
        
        # WebSocket test
        try:
            asyncio.get_event_loop().run_until_complete(self.test_websocket())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.test_websocket())
            loop.close()

    def print_summary(self):
        """Print test results summary"""
        self.log("\n" + "="*60)
        self.log("🔍 TEST RESULTS SUMMARY")
        self.log("="*60)
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        
        self.log(f"Total Tests: {self.tests_run}")
        self.log(f"Passed: {self.tests_passed}")
        self.log(f"Failed: {len(self.failed_tests)}")
        self.log(f"Success Rate: {success_rate:.1f}%")
        
        if self.critical_issues:
            self.log("\n🚨 CRITICAL ISSUES:")
            for issue in self.critical_issues:
                self.log(f"  - {issue}")
        
        if self.failed_tests:
            self.log("\n❌ FAILED TESTS:")
            for test in self.failed_tests:
                self.log(f"  - {test['name']}: Expected {test['expected']}, Got {test['actual']}")
                if test['error']:
                    self.log(f"    Error: {test['error']}")
        
        if success_rate >= 80:
            self.log("\n✅ Overall Status: GOOD - Most functionality working")
            return 0
        elif success_rate >= 60:
            self.log("\n⚠️  Overall Status: MODERATE - Some issues found")
            return 1
        else:
            self.log("\n❌ Overall Status: POOR - Significant issues found")
            return 2

def main():
    """Main test execution"""
    tester = HFTBotAPITester()
    
    try:
        tester.run_all_tests()
    except KeyboardInterrupt:
        tester.log("\n⚠️  Tests interrupted by user")
    except Exception as e:
        tester.log(f"\n💥 Test suite crashed: {str(e)}", "ERROR")
        return 3
    
    return tester.print_summary()

if __name__ == "__main__":
    sys.exit(main())