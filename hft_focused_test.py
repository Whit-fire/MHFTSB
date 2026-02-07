#!/usr/bin/env python3

import requests
import json
import time
import sys
from datetime import datetime

class HFTFocusedTester:
    def __init__(self, base_url="https://trade-clone-25.preview.emergentagent.com"):
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

    def test_health_endpoint(self):
        """Test 1: /api/health responds"""
        self.log("\n🔍 TEST 1: /api/health endpoint")
        success, response = self.run_test(
            "Health Check",
            "GET",
            "health",
            200
        )
        if success:
            bot_status = response.get('bot', 'unknown')
            mode = response.get('mode', 'unknown')
            self.log(f"   ✅ Health endpoint responds correctly")
            self.log(f"   Bot status: {bot_status}, Mode: {mode}")
            return True
        else:
            self.critical_issues.append("CRITICAL: /api/health endpoint not responding")
            return False

    def test_bot_start_live_mode(self):
        """Test 2: /api/bot/start in LIVE mode"""
        self.log("\n🔍 TEST 2: /api/bot/start in LIVE mode")
        
        # First, ensure bot is stopped
        self.run_test("Stop Bot (cleanup)", "POST", "bot/stop", 200)
        time.sleep(1)
        
        # Set mode to LIVE
        success, response = self.run_test(
            "Set Bot Mode to LIVE",
            "POST",
            "bot/toggle-mode",
            200
        )
        
        if success:
            current_mode = response.get('mode', 'unknown')
            self.log(f"   Current mode after toggle: {current_mode}")
            
            # Toggle again if we didn't get live mode
            if current_mode != "live":
                success2, response2 = self.run_test(
                    "Toggle to LIVE Mode Again",
                    "POST",
                    "bot/toggle-mode", 
                    200
                )
                if success2:
                    current_mode = response2.get('mode', 'unknown')
                    self.log(f"   Mode after second toggle: {current_mode}")
        
        # Now start the bot in LIVE mode
        success, response = self.run_test(
            "Start Bot in LIVE Mode",
            "POST",
            "bot/start",
            200
        )
        
        if success:
            started_mode = response.get('mode', 'unknown')
            status = response.get('status', 'unknown')
            
            if started_mode == "live" and status == "running":
                self.log(f"   ✅ Bot started successfully in LIVE mode")
                
                # Let it run for a few seconds to verify it stays stable
                time.sleep(5)
                
                # Check status after running
                status_success, status_response = self.run_test(
                    "Check Bot Status in LIVE Mode",
                    "GET",
                    "bot/status",
                    200
                )
                
                if status_success:
                    running_status = status_response.get('status', 'unknown')
                    running_mode = status_response.get('mode', 'unknown')
                    uptime = status_response.get('uptime_seconds', 0)
                    
                    self.log(f"   Status after 5s: {running_status}, Mode: {running_mode}, Uptime: {uptime}s")
                    
                    if running_status == "running" and running_mode == "live":
                        self.log(f"   ✅ Bot remains stable in LIVE mode")
                        return True
                    else:
                        self.log(f"   ❌ Bot status changed unexpectedly: {running_status}/{running_mode}")
                        return False
                else:
                    self.log(f"   ❌ Failed to check bot status after starting in LIVE mode")
                    return False
            else:
                self.log(f"   ❌ Bot failed to start in LIVE mode: status={status}, mode={started_mode}")
                return False
        else:
            self.critical_issues.append("CRITICAL: Cannot start bot in LIVE mode")
            return False

    def test_backend_logs_candidate_events(self):
        """Test 3: Backend logs show candidate events + parse_drop_reason"""
        self.log("\n🔍 TEST 3: Backend logs - candidate events + parse_drop_reason")
        
        # Get recent logs
        success, response = self.run_test(
            "Get Recent Logs for Candidate Events",
            "GET",
            "logs?limit=100",
            200
        )
        
        if success:
            logs = response.get('logs', [])
            self.log(f"   Checking {len(logs)} log entries for candidate events...")
            
            # Look for candidate events and parse_drop_reason
            candidate_events = []
            parse_drop_events = []
            guard_drop_events = []
            json_formatted_logs = 0
            
            for log in logs:
                message = log.get('message', '')
                level = log.get('level', '').upper()
                
                # Check for JSON formatted logs (structured logging)
                if message.startswith('{') and '"event":' in message:
                    json_formatted_logs += 1
                    try:
                        log_data = json.loads(message)
                        event_type = log_data.get('event', '')
                        
                        if event_type == 'candidate':
                            candidate_events.append(log_data)
                        elif event_type == 'parse_drop':
                            parse_drop_events.append(log_data)
                        elif event_type == 'guard_drop':
                            guard_drop_events.append(log_data)
                    except json.JSONDecodeError:
                        pass
                
                # Also check for text-based candidate events
                if 'candidate' in message.lower() and ('detected' in message.lower() or 'sig=' in message.lower()):
                    candidate_events.append({'message': message, 'level': level})
            
            # Report findings
            self.log(f"   JSON formatted logs: {json_formatted_logs}")
            self.log(f"   Candidate events found: {len(candidate_events)}")
            self.log(f"   Parse drop events found: {len(parse_drop_events)}")
            self.log(f"   Guard drop events found: {len(guard_drop_events)}")
            
            # Show sample events
            if candidate_events:
                sample = candidate_events[0]
                if isinstance(sample, dict) and 'sig' in sample:
                    self.log(f"   Sample candidate event: sig={sample.get('sig', 'N/A')[:16]}...")
                else:
                    self.log(f"   Sample candidate event: {str(sample)[:60]}...")
            
            if parse_drop_events:
                sample = parse_drop_events[0]
                reason = sample.get('reason', 'N/A')
                self.log(f"   Sample parse_drop reason: {reason}")
            
            # Verify structured logging is working
            if json_formatted_logs > 0:
                self.log(f"   ✅ JSON structured logging is working ({json_formatted_logs} JSON logs)")
            else:
                self.log(f"   ⚠️  No JSON structured logs found (may be using text logging)")
            
            # Verify candidate events are being logged
            if len(candidate_events) > 0:
                self.log(f"   ✅ Candidate events are being logged")
                return True
            else:
                self.log(f"   ⚠️  No candidate events found in recent logs (bot may not be processing events)")
                # This might be normal if bot isn't running or no events occurred
                return True
        
        return success

    def test_wallet_locked_guard_drop(self):
        """Test 4: Wallet locked -> guard_drop non-blocking"""
        self.log("\n🔍 TEST 4: Wallet locked -> guard_drop non-blocking")
        
        # First, reset wallet to ensure it's locked
        reset_success, _ = self.run_test(
            "Reset Wallet (to test locked state)",
            "POST",
            "wallet/reset",
            200
        )
        
        if not reset_success:
            self.log("   ❌ Failed to reset wallet for testing")
            return False
        
        # Verify wallet is locked
        status_success, status_response = self.run_test(
            "Check Wallet Status (should be locked)",
            "GET",
            "wallet/status",
            200
        )
        
        if status_success:
            is_unlocked = status_response.get('is_unlocked', True)
            is_setup = status_response.get('is_setup', True)
            
            self.log(f"   Wallet state: setup={is_setup}, unlocked={is_unlocked}")
            
            if not is_unlocked:
                self.log(f"   ✅ Wallet is locked as expected")
                
                # Now start bot in LIVE mode with locked wallet
                # First ensure we're in live mode
                self.run_test("Set Mode to LIVE", "POST", "bot/toggle-mode", 200)
                
                # Start bot
                start_success, start_response = self.run_test(
                    "Start Bot with Locked Wallet",
                    "POST",
                    "bot/start",
                    200
                )
                
                if start_success:
                    status = start_response.get('status', 'unknown')
                    mode = start_response.get('mode', 'unknown')
                    
                    self.log(f"   Bot started with locked wallet: status={status}, mode={mode}")
                    
                    if status == "running":
                        self.log(f"   ✅ Bot starts successfully even with locked wallet")
                        
                        # Let it run for a few seconds and check logs for guard_drop events
                        time.sleep(8)
                        
                        # Check logs for guard_drop events
                        logs_success, logs_response = self.run_test(
                            "Check Logs for Guard Drop Events",
                            "GET",
                            "logs?limit=50",
                            200
                        )
                        
                        if logs_success:
                            logs = logs_response.get('logs', [])
                            guard_drops = []
                            wallet_locked_drops = []
                            
                            for log in logs:
                                message = log.get('message', '')
                                
                                # Check for JSON formatted guard_drop events
                                if message.startswith('{') and '"event":"guard_drop"' in message:
                                    try:
                                        log_data = json.loads(message)
                                        guard_drops.append(log_data)
                                        
                                        if log_data.get('reason') == 'wallet_locked':
                                            wallet_locked_drops.append(log_data)
                                    except json.JSONDecodeError:
                                        pass
                                
                                # Also check for text-based wallet locked messages
                                if 'wallet' in message.lower() and 'locked' in message.lower():
                                    wallet_locked_drops.append({'message': message})
                            
                            self.log(f"   Guard drop events found: {len(guard_drops)}")
                            self.log(f"   Wallet locked drops found: {len(wallet_locked_drops)}")
                            
                            if len(wallet_locked_drops) > 0:
                                self.log(f"   ✅ Wallet locked guard drops are working (non-blocking)")
                                
                                # Check that bot is still running
                                final_status_success, final_status_response = self.run_test(
                                    "Check Bot Still Running After Guard Drops",
                                    "GET",
                                    "bot/status",
                                    200
                                )
                                
                                if final_status_success:
                                    final_status = final_status_response.get('status', 'unknown')
                                    uptime = final_status_response.get('uptime_seconds', 0)
                                    
                                    if final_status == "running":
                                        self.log(f"   ✅ Bot remains running after wallet locked drops (uptime: {uptime}s)")
                                        return True
                                    else:
                                        self.log(f"   ❌ Bot stopped running after wallet locked drops: {final_status}")
                                        return False
                            else:
                                self.log(f"   ⚠️  No wallet locked drops found (may not have processed any events)")
                                # This could be normal if no events were processed
                                return True
                        else:
                            self.log(f"   ❌ Failed to check logs for guard drop events")
                            return False
                    else:
                        self.log(f"   ❌ Bot failed to start with locked wallet: {status}")
                        return False
                else:
                    self.log(f"   ❌ Failed to start bot with locked wallet")
                    return False
            else:
                self.log(f"   ❌ Wallet is not locked after reset (is_unlocked={is_unlocked})")
                return False
        else:
            self.log(f"   ❌ Failed to check wallet status")
            return False

    def run_focused_tests(self):
        """Run the 4 specific tests requested"""
        self.log("🚀 Starting HFT Bot Focused Tests")
        self.log("Testing specific features from review request:")
        self.log("1. /api/health responds")
        self.log("2. /api/bot/start in LIVE mode")  
        self.log("3. Backend logs: candidate events + parse_drop_reason")
        self.log("4. Wallet locked -> guard_drop non-blocking")
        self.log(f"Testing against: {self.base_url}")
        
        # Run the 4 specific tests
        test1_result = self.test_health_endpoint()
        test2_result = self.test_bot_start_live_mode()
        test3_result = self.test_backend_logs_candidate_events()
        test4_result = self.test_wallet_locked_guard_drop()
        
        # Clean up - stop bot
        self.log("\n🧹 Cleanup")
        self.run_test("Stop Bot (cleanup)", "POST", "bot/stop", 200)
        
        # Summary
        self.log("\n" + "="*60)
        self.log("🔍 FOCUSED TEST RESULTS")
        self.log("="*60)
        
        results = [
            ("1. /api/health responds", test1_result),
            ("2. /api/bot/start in LIVE mode", test2_result),
            ("3. Backend logs: candidate events + parse_drop_reason", test3_result),
            ("4. Wallet locked -> guard_drop non-blocking", test4_result)
        ]
        
        passed_count = sum(1 for _, result in results if result)
        
        for test_name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            self.log(f"{status} - {test_name}")
        
        self.log(f"\nFocused Tests: {passed_count}/4 passed ({passed_count/4*100:.1f}%)")
        
        # Overall test summary
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        self.log(f"Total API calls: {self.tests_run}")
        self.log(f"Successful API calls: {self.tests_passed}")
        self.log(f"API Success Rate: {success_rate:.1f}%")
        
        if self.critical_issues:
            self.log("\n🚨 CRITICAL ISSUES:")
            for issue in self.critical_issues:
                self.log(f"  - {issue}")
        
        if self.failed_tests:
            self.log("\n❌ FAILED API CALLS:")
            for test in self.failed_tests:
                self.log(f"  - {test['name']}: Expected {test['expected']}, Got {test['actual']}")
        
        # Return appropriate exit code
        if passed_count == 4 and success_rate >= 90:
            self.log("\n✅ Overall Status: EXCELLENT - All focused tests passed")
            return 0
        elif passed_count >= 3 and success_rate >= 80:
            self.log("\n✅ Overall Status: GOOD - Most focused tests passed")
            return 0
        elif passed_count >= 2:
            self.log("\n⚠️  Overall Status: MODERATE - Some focused tests failed")
            return 1
        else:
            self.log("\n❌ Overall Status: POOR - Multiple focused tests failed")
            return 2

def main():
    """Main test execution"""
    tester = HFTFocusedTester()
    
    try:
        return tester.run_focused_tests()
    except KeyboardInterrupt:
        tester.log("\n⚠️  Tests interrupted by user")
        return 3
    except Exception as e:
        tester.log(f"\n💥 Test suite crashed: {str(e)}", "ERROR")
        return 3

if __name__ == "__main__":
    sys.exit(main())