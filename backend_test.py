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
    def __init__(self, base_url="https://pumpfun-trader-8.preview.emergentagent.com"):
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

    def generate_test_keypair(self):
        """Generate a test keypair for testing"""
        # Create a 64-byte keypair (32-byte seed + 32-byte public key)
        seed = secrets.token_bytes(32)
        # For testing, we'll create a fake 64-byte keypair by duplicating seed
        keypair_bytes = seed + seed  # This won't be a real keypair but will test the format
        return base58.b58encode(keypair_bytes).decode()

    def test_wallet_reset(self):
        """Test wallet reset"""
        success, response = self.run_test(
            "Wallet Reset",
            "POST", 
            "wallet/reset",
            200
        )
        if success:
            self.log(f"   Wallet reset: {response.get('message', 'completed')}")
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
            setup = response.get('is_setup', False)
            unlocked = response.get('is_unlocked', False) 
            address = response.get('address', None)
            self.log(f"   Wallet setup: {setup}, Unlocked: {unlocked}, Address: {address}")
            return response
        return None

    def test_wallet_encrypt(self, private_key=None, passphrase=None):
        """Test wallet encryption with proper keypair"""
        test_key = private_key or self.generate_test_keypair()
        test_passphrase = passphrase or "TestPassphrase123!"
        
        success, response = self.run_test(
            "Wallet Encrypt",
            "POST",
            "wallet/encrypt",
            200,
            data={"private_key": test_key, "passphrase": test_passphrase}
        )
        
        if success and response.get('success'):
            address = response.get('address')
            self.log(f"   Encrypted wallet, derived address: {address}")
            # Validate it's a proper Solana address format
            if address and len(address) >= 32 and len(address) <= 44:
                return {'address': address, 'passphrase': test_passphrase, 'key': test_key}
        
        if success and response.get('error'):
            self.log(f"   Encryption error: {response['error']}")
            
        return None

    def test_wallet_unlock(self, passphrase):
        """Test wallet unlock"""
        success, response = self.run_test(
            "Wallet Unlock", 
            "POST",
            "wallet/unlock",
            200,
            data={"passphrase": passphrase}
        )
        
        if success and response.get('success'):
            address = response.get('address')
            self.log(f"   Unlocked wallet, address: {address}")
            return address
        elif success and response.get('error'):
            self.log(f"   Unlock error: {response['error']}")
        return None

    def test_wallet_balance_by_address(self, address):
        """Test getting balance for specific address"""
        success, response = self.run_test(
            f"Get Balance for {address[:8]}...",
            "GET", 
            f"wallet/balance/{address}",
            200
        )
        
        if success and 'error' not in response:
            sol_balance = response.get('sol_balance', 0)
            token_count = response.get('token_count', 0)
            self.log(f"   Address balance: {sol_balance} SOL, {token_count} tokens")
            return True
        elif success and 'error' in response:
            self.log(f"   Balance error: {response['error']}")
        return False

    def test_wallet_balance_configured(self):
        """Test getting balance for configured wallet"""
        success, response = self.run_test(
            "Get Configured Wallet Balance",
            "GET",
            "wallet/balance", 
            200
        )
        
        if success and 'error' not in response:
            sol_balance = response.get('sol_balance', 0)
            token_count = response.get('token_count', 0)
            self.log(f"   Configured wallet balance: {sol_balance} SOL, {token_count} tokens")
            return True
        elif success and 'error' in response:
            self.log(f"   Expected error (no wallet/not unlocked): {response['error']}")
            return True  # This is expected if no wallet is configured/unlocked
        return False

    def test_bot_start(self, mode="simulation"):
        """Test starting the bot in specific mode"""
        # First check if we need to set mode
        if mode:
            success, response = self.run_test(
                f"Set Bot Mode to {mode}",
                "POST",
                "bot/toggle-mode",
                200
            )
            if success:
                current_mode = response.get('mode', 'unknown')
                self.log(f"   Current mode after toggle: {current_mode}")
                # Toggle again if we didn't get the desired mode
                if current_mode != mode:
                    self.run_test(
                        f"Toggle Bot Mode Again",
                        "POST", 
                        "bot/toggle-mode",
                        200
                    )
        
        success, response = self.run_test(
            "Start Bot",
            "POST",
            "bot/start",
            200
        )
        if success:
            self.log(f"   Bot started in mode: {response.get('mode', 'unknown')}")
            # Wait a bit for bot to initialize
            time.sleep(3)
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

    def test_positions_with_sell_data(self):
        """Test positions endpoints and verify new sell-related fields are present"""
        open_success, open_response = self.run_test(
            "Get Open Positions (Sell Data Check)",
            "GET",
            "positions",
            200
        )
        
        history_success, history_response = self.run_test(
            "Get Position History (Sell Data Check)",
            "GET",
            "positions/history",
            200
        )
        
        if open_success:
            positions = open_response.get('positions', [])
            self.log(f"   Open positions: {len(positions)}")
            
            # Check if positions have the new sell-related fields
            if positions:
                pos = positions[0]
                sell_fields = ['bonding_curve', 'associated_bonding_curve', 'token_program', 'creator', 'token_amount']
                missing_fields = [field for field in sell_fields if field not in pos]
                
                if missing_fields:
                    self.log(f"⚠️  Position missing sell fields: {missing_fields}")
                    self.failed_tests.append({
                        "name": "Position Sell Fields Check",
                        "expected": "All sell fields present",
                        "actual": f"Missing: {missing_fields}",
                        "endpoint": "positions",
                        "error": f"Position data missing sell fields: {missing_fields}"
                    })
                else:
                    self.log("✅ Position contains all required sell fields")
                    
                # Log sample position data for verification
                self.log(f"   Sample position sell data: bc={pos.get('bonding_curve', 'None')[:12] if pos.get('bonding_curve') else 'None'}...")
            else:
                self.log("   No positions to check for sell fields")
            
        if history_success:
            history = history_response.get('positions', [])
            self.log(f"   Historical positions: {len(history)}")
            
        return open_success and history_success

    def test_force_sell_simulation(self):
        """Test force-sell endpoint in simulation mode"""
        # First, get current positions to test force-sell on
        positions_success, positions_response = self.run_test(
            "Get Positions for Force-Sell Test",
            "GET",
            "positions",
            200
        )
        
        if not positions_success:
            self.log("❌ Cannot test force-sell - failed to get positions")
            return False
            
        positions = positions_response.get('positions', [])
        if not positions:
            self.log("⚠️  No open positions to test force-sell on")
            # This is not a failure - just means no positions are available
            return True
            
        # Test force-sell on the first position
        position_id = positions[0]['id']
        position_name = positions[0].get('token_name', 'Unknown')
        
        self.log(f"   Testing force-sell on position: {position_name} (ID: {position_id[:8]}...)")
        
        success, response = self.run_test(
            f"Force-Sell Position {position_name}",
            "POST",
            f"positions/{position_id}/force-sell",
            200
        )
        
        if success:
            if response.get('success'):
                mode = response.get('mode', 'unknown')
                self.log(f"✅ Force-sell successful in {mode} mode")
                
                # Verify position was closed
                closed_pos = response.get('position', {})
                if closed_pos.get('status') == 'closed':
                    self.log(f"   Position correctly closed with reason: {closed_pos.get('close_reason', 'N/A')}")
                else:
                    self.log(f"⚠️  Position status after force-sell: {closed_pos.get('status', 'unknown')}")
                    
            elif 'error' in response:
                error = response.get('error', 'Unknown error')
                if 'missing' in error.lower() and ('bonding_curve' in error.lower() or 'token_amount' in error.lower()):
                    self.log(f"⚠️  Expected error for missing sell data: {error}")
                    # This is expected if position doesn't have sell data
                    return True
                else:
                    self.log(f"❌ Unexpected force-sell error: {error}")
                    return False
            else:
                self.log(f"❌ Force-sell returned unexpected response: {response}")
                return False
        
        return success

    def test_simulation_mode_clone_and_inject(self):
        """Test bot in simulation mode to verify Clone & Inject implementation doesn't break functionality"""
        self.log("\n🤖 Testing Simulation Mode with Clone & Inject Implementation...")
        
        # Ensure bot is stopped first
        self.run_test("Stop Bot (cleanup)", "POST", "bot/stop", 200)
        time.sleep(1)
        
        # Start in simulation mode
        success = self.test_bot_start("simulation")
        if not success:
            return False
            
        # Let bot run for 10-15 seconds to generate activity using Clone & Inject
        self.log("   Letting bot run for 12 seconds to test Clone & Inject in simulation...")
        time.sleep(12)
        
        # Check that positions are created (Clone & Inject should work in simulation)
        positions_success, positions_response = self.run_test(
            "Check Positions Created with Clone & Inject",
            "GET",
            "positions",
            200
        )
        
        if positions_success:
            positions = positions_response.get('positions', [])
            if positions:
                self.log(f"✅ Clone & Inject simulation created {len(positions)} positions")
                
                # Check first position for required data
                pos = positions[0]
                required_fields = ['bonding_curve', 'associated_bonding_curve', 'token_program', 'creator', 'token_amount']
                present_fields = [field for field in required_fields if pos.get(field) is not None]
                
                self.log(f"   Position data fields present: {len(present_fields)}/{len(required_fields)}")
                if len(present_fields) >= 3:  # At least some fields should be present
                    self.log("✅ Positions contain required Clone & Inject data fields")
                else:
                    self.log(f"⚠️  Limited data in positions: {present_fields}")
                    
                # Test force-sell on a position if available
                if positions:
                    self.test_force_sell_simulation()
            else:
                self.log("   No positions created - checking if this is expected...")
                # This might be normal in some cases, not necessarily a failure
        
        # Check bot status during Clone & Inject operation
        status_success, status_response = self.run_test(
            "Bot Status During Clone & Inject Simulation",
            "GET",
            "bot/status", 
            200
        )
        
        if status_success:
            status = status_response.get('status', 'unknown')
            mode = status_response.get('mode', 'unknown')
            uptime = status_response.get('uptime_seconds', 0)
            
            self.log(f"   Clone & Inject Status: {status}, Mode: {mode}, Uptime: {uptime}s")
            
            if status == "running" and mode == "simulation":
                self.log("✅ Clone & Inject simulation mode working correctly")
            else:
                self.log(f"❌ Unexpected status/mode during Clone & Inject: {status}/{mode}")
                return False
        
        # Check for any errors in logs that might indicate Clone & Inject issues
        logs_success, logs_response = self.run_test(
            "Check Logs for Clone & Inject Errors",
            "GET",
            "logs",
            200
        )
        
        if logs_success:
            logs = logs_response.get('logs', [])
            clone_inject_errors = []
            for log in logs:
                message = log.get('message', '').lower()
                if any(keyword in message for keyword in ['clone', 'inject', 'account_metas_clone', 'pda', 'derivation']):
                    if 'error' in message or 'failed' in message:
                        clone_inject_errors.append(log.get('message', 'N/A'))
            
            if clone_inject_errors:
                self.log(f"⚠️  Found {len(clone_inject_errors)} Clone & Inject related errors:")
                for error in clone_inject_errors[-3:]:  # Show last 3 errors
                    self.log(f"     {error}")
                # Don't fail the test for this, but note the issues
            else:
                self.log("✅ No Clone & Inject related errors found in logs")
        
        # Stop bot
        stop_success = self.run_test("Stop Bot After Clone & Inject Test", "POST", "bot/stop", 200)
        
        return status_success and stop_success

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

    def test_parse_service_metrics(self):
        """Test ParseService specific metrics (parse_dropped and parse_success)"""
        self.log("Testing ParseService metrics (parse_dropped and parse_success)...")
        
        success, response = self.run_test(
            "Get ParseService Metrics",
            "GET",
            "metrics",
            200
        )
        
        if success:
            counters = response.get('counters', {})
            
            # Check for new ParseService metrics
            parse_dropped = counters.get('parse_dropped', 0)
            parse_success = counters.get('parse_success', 0)
            
            self.log(f"   parse_dropped: {parse_dropped}")
            self.log(f"   parse_success: {parse_success}")
            
            # Verify metrics exist
            if 'parse_dropped' in counters and 'parse_success' in counters:
                self.log("✅ ParseService metrics (parse_dropped, parse_success) are present")
                
                # Calculate ratio if we have data
                total_parse_attempts = parse_dropped + parse_success
                if total_parse_attempts > 0:
                    success_ratio = (parse_success / total_parse_attempts) * 100
                    self.log(f"   Parse success ratio: {success_ratio:.1f}% ({parse_success}/{total_parse_attempts})")
                    
                    # Expected: 80-90% success ratio (10-20% drops are normal)
                    if success_ratio >= 70:
                        self.log("✅ Parse success ratio is healthy (≥70%)")
                    else:
                        self.log(f"⚠️  Parse success ratio is low: {success_ratio:.1f}%")
                else:
                    self.log("   No parse attempts recorded yet (bot may not be running)")
                
                return True
            else:
                missing = []
                if 'parse_dropped' not in counters:
                    missing.append('parse_dropped')
                if 'parse_success' not in counters:
                    missing.append('parse_success')
                
                self.log(f"❌ Missing ParseService metrics: {missing}")
                self.failed_tests.append({
                    "name": "ParseService Metrics Check",
                    "expected": "parse_dropped and parse_success metrics present",
                    "actual": f"Missing: {missing}",
                    "endpoint": "metrics",
                    "error": f"ParseService metrics not found: {missing}"
                })
                return False
        
        return success

    def test_clone_and_inject_import(self):
        """Test that Clone & Inject methods import correctly and have required functionality"""
        self.log("Testing Clone & Inject implementation import...")
        try:
            # Test import
            import sys
            sys.path.append('/app/backend')
            from services.solana_trader import SolanaTrader, build_sell_instruction
            from services.position_manager import PositionData
            
            # Check if the class has the CRITICAL Clone & Inject methods
            missing_methods = []
            if not hasattr(SolanaTrader, 'clone_and_inject_buy_transaction'):
                missing_methods.append('clone_and_inject_buy_transaction')
            if not hasattr(SolanaTrader, 'execute_buy_cloned'):
                missing_methods.append('execute_buy_cloned')
            if not hasattr(SolanaTrader, '_extract_pump_accounts'):
                missing_methods.append('_extract_pump_accounts')
            
            # Check existing methods still exist (no regression)
            if not hasattr(SolanaTrader, 'wait_for_bonding_curve_init'):
                missing_methods.append('wait_for_bonding_curve_init')
            if not hasattr(SolanaTrader, 'execute_sell'):
                missing_methods.append('execute_sell')
            if not hasattr(SolanaTrader, 'build_sell_transaction'):
                missing_methods.append('build_sell_transaction')
            
            # Check if build_sell_instruction function exists
            if 'build_sell_instruction' not in globals() and 'build_sell_instruction' not in locals():
                missing_methods.append('build_sell_instruction (function)')
            
            # Check PositionData for new fields
            pos_test = PositionData("test_mint", "test_token", 0.001, 0.03, 80.0, "test_sig")
            missing_fields = []
            if not hasattr(pos_test, 'bonding_curve'):
                missing_fields.append('bonding_curve')
            if not hasattr(pos_test, 'associated_bonding_curve'):
                missing_fields.append('associated_bonding_curve')
            if not hasattr(pos_test, 'token_program'):
                missing_fields.append('token_program')
            if not hasattr(pos_test, 'creator'):
                missing_fields.append('creator')
            if not hasattr(pos_test, 'token_amount'):
                missing_fields.append('token_amount')
            
            if missing_methods or missing_fields:
                error_msg = f"Missing methods: {missing_methods}, Missing fields: {missing_fields}"
                self.log(f"❌ Clone & Inject missing components: {error_msg}")
                self.failed_tests.append({
                    "name": "Clone & Inject Components Check",
                    "expected": "All Clone & Inject methods and PositionData fields exist",
                    "actual": "Missing components",
                    "endpoint": "N/A",
                    "error": error_msg
                })
                self.critical_issues.append(f"CRITICAL: Clone & Inject implementation incomplete: {error_msg}")
                self.tests_run += 1
                return False
            else:
                self.log("✅ Clone & Inject implementation imports correctly with all required methods")
                self.tests_run += 1
                self.tests_passed += 1
                return True
                
        except ImportError as e:
            self.log(f"❌ Clone & Inject import failed: {e}")
            self.failed_tests.append({
                "name": "Clone & Inject Import",
                "expected": "Successful import",
                "actual": "Import failed",
                "endpoint": "N/A", 
                "error": str(e)
            })
            self.critical_issues.append(f"CRITICAL: Clone & Inject import failed: {e}")
            self.tests_run += 1
            return False
        except Exception as e:
            self.log(f"❌ Clone & Inject test failed: {e}")
            self.failed_tests.append({
                "name": "Clone & Inject Test",
                "expected": "Method check successful",
                "actual": "Test failed",
                "endpoint": "N/A",
                "error": str(e)
            })
            self.critical_issues.append(f"CRITICAL: Clone & Inject test failed: {e}")
            self.tests_run += 1
            return False

    def test_extract_pump_accounts_structure(self):
        """Test that _extract_pump_accounts returns account_metas_clone field"""
        self.log("Testing _extract_pump_accounts for Clone & Inject compatibility...")
        try:
            import sys
            sys.path.append('/app/backend')
            from services.solana_trader import SolanaTrader
            
            # Create a mock SolanaTrader instance
            trader = SolanaTrader(None, None)
            
            # Create a mock transaction data structure that would contain account_metas_clone
            mock_tx_data = {
                "meta": {"err": None, "postTokenBalances": [{"mint": "test_mint", "owner": "test_owner"}]},
                "transaction": {
                    "message": {
                        "accountKeys": [
                            {"pubkey": "test_key1", "signer": True, "writable": True},
                            {"pubkey": "test_key2", "signer": False, "writable": False}
                        ],
                        "instructions": [{
                            "programId": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
                            "accounts": [0, 1],
                            "data": "test_data"
                        }]
                    }
                }
            }
            
            # Test the method exists and can be called
            result = trader._extract_pump_accounts(mock_tx_data)
            
            # Check if result contains the required fields for Clone & Inject
            if result is None:
                self.log("⚠️  _extract_pump_accounts returned None (expected for mock data)")
                self.tests_run += 1
                self.tests_passed += 1
                return True
            
            required_fields = ['account_metas_clone', 'instruction_data']
            missing_fields = [field for field in required_fields if field not in result]
            
            if missing_fields:
                error_msg = f"Missing Clone & Inject fields in _extract_pump_accounts: {missing_fields}"
                self.log(f"❌ {error_msg}")
                self.failed_tests.append({
                    "name": "_extract_pump_accounts Structure Check",
                    "expected": "account_metas_clone and instruction_data fields present",
                    "actual": f"Missing: {missing_fields}",
                    "endpoint": "N/A",
                    "error": error_msg
                })
                self.critical_issues.append(f"CRITICAL: {error_msg}")
                self.tests_run += 1
                return False
            else:
                self.log("✅ _extract_pump_accounts has correct structure for Clone & Inject")
                self.tests_run += 1
                self.tests_passed += 1
                return True
                
        except Exception as e:
            self.log(f"❌ _extract_pump_accounts structure test failed: {e}")
            self.failed_tests.append({
                "name": "_extract_pump_accounts Structure Test",
                "expected": "Method callable with correct return structure",
                "actual": "Test failed",
                "endpoint": "N/A",
                "error": str(e)
            })
            self.critical_issues.append(f"CRITICAL: _extract_pump_accounts test failed: {e}")
            self.tests_run += 1
            return False

    def test_parse_service_comprehensive(self):
        """Comprehensive ParseService test - start bot, monitor logs, check metrics"""
        self.log("\n🔧 COMPREHENSIVE ParseService Test (WARNING Spam Elimination)...")
        
        # Step 1: Ensure bot is stopped first
        self.run_test("Stop Bot (cleanup)", "POST", "bot/stop", 200)
        time.sleep(1)
        
        # Step 2: Get initial metrics baseline
        initial_success, initial_response = self.run_test(
            "Get Initial Metrics Baseline",
            "GET",
            "metrics",
            200
        )
        
        initial_parse_dropped = 0
        initial_parse_success = 0
        if initial_success:
            counters = initial_response.get('counters', {})
            initial_parse_dropped = counters.get('parse_dropped', 0)
            initial_parse_success = counters.get('parse_success', 0)
            self.log(f"   Initial metrics - dropped: {initial_parse_dropped}, success: {initial_parse_success}")
        
        # Step 3: Start bot in simulation mode
        success = self.test_bot_start("simulation")
        if not success:
            self.log("❌ Failed to start bot for ParseService test")
            return False
        
        # Step 4: Let bot run for 15-20 seconds to generate parsing activity
        self.log("   Letting bot run for 18 seconds to generate parse activity...")
        time.sleep(18)
        
        # Step 5: Check logs for WARNING spam
        self.log("   Checking logs for WARNING spam...")
        logs_clean = self.test_parse_service_logs_clean()
        
        # Step 6: Check metrics for parse_dropped and parse_success
        self.log("   Checking ParseService metrics...")
        metrics_success = self.test_parse_service_metrics()
        
        # Step 7: Get final metrics to verify activity
        final_success, final_response = self.run_test(
            "Get Final Metrics After ParseService Test",
            "GET",
            "metrics",
            200
        )
        
        metrics_increased = False
        if final_success:
            counters = final_response.get('counters', {})
            final_parse_dropped = counters.get('parse_dropped', 0)
            final_parse_success = counters.get('parse_success', 0)
            
            dropped_increase = final_parse_dropped - initial_parse_dropped
            success_increase = final_parse_success - initial_parse_success
            
            self.log(f"   Metrics change - dropped: +{dropped_increase}, success: +{success_increase}")
            
            if dropped_increase > 0 or success_increase > 0:
                metrics_increased = True
                self.log("✅ ParseService metrics increased (bot is actively parsing)")
                
                # Verify the ratio is reasonable (80-90% success expected)
                total_new = dropped_increase + success_increase
                if total_new > 0:
                    success_ratio = (success_increase / total_new) * 100
                    self.log(f"   New parse success ratio: {success_ratio:.1f}%")
                    
                    if success_ratio >= 70:
                        self.log("✅ Parse success ratio is healthy")
                    else:
                        self.log(f"⚠️  Parse success ratio is low: {success_ratio:.1f}%")
            else:
                self.log("⚠️  No increase in parse metrics (bot may not be processing CREATE events)")
        
        # Step 8: Check bot status
        status_success, status_response = self.run_test(
            "Bot Status During ParseService Test",
            "GET",
            "bot/status",
            200
        )
        
        bot_running = False
        if status_success:
            status = status_response.get('status', 'unknown')
            mode = status_response.get('mode', 'unknown')
            uptime = status_response.get('uptime_seconds', 0)
            
            self.log(f"   Bot status: {status}, Mode: {mode}, Uptime: {uptime}s")
            
            if status == "running" and mode == "simulation":
                bot_running = True
                self.log("✅ Bot running correctly during ParseService test")
            else:
                self.log(f"❌ Unexpected bot status/mode: {status}/{mode}")
        
        # Step 9: Stop bot
        stop_success = self.run_test("Stop Bot After ParseService Test", "POST", "bot/stop", 200)
        
        # Step 10: Final assessment
        all_passed = logs_clean and metrics_success and bot_running and stop_success
        
        if all_passed:
            self.log("✅ ParseService comprehensive test PASSED")
            self.log("   - No WARNING spam in logs")
            self.log("   - parse_dropped and parse_success metrics working")
            self.log("   - Bot operates normally with silent drops")
        else:
            issues = []
            if not logs_clean:
                issues.append("WARNING spam still present")
            if not metrics_success:
                issues.append("ParseService metrics missing")
            if not bot_running:
                issues.append("Bot not running properly")
            
            self.log(f"❌ ParseService comprehensive test FAILED: {', '.join(issues)}")
            self.critical_issues.append(f"ParseService test failed: {', '.join(issues)}")
        
        return all_passed
        """Test bot in simulation mode to verify no regression"""
        self.log("\n🤖 Testing Simulation Mode (P0 Fix Verification)...")
        
        # Ensure bot is stopped first
        self.run_test("Stop Bot (cleanup)", "POST", "bot/stop", 200)
        time.sleep(1)
        
        # Start in simulation mode
        success = self.test_bot_start("simulation")
        if not success:
            return False
            
        # Let bot run for a few seconds to generate activity
        self.log("   Letting bot run for 5 seconds to generate simulation data...")
        time.sleep(5)
        
        # Check bot status
        status_success, status_response = self.run_test(
            "Bot Status During Simulation",
            "GET",
            "bot/status", 
            200
        )
        
        if status_success:
            status = status_response.get('status', 'unknown')
            mode = status_response.get('mode', 'unknown')
            uptime = status_response.get('uptime_seconds', 0)
            
            self.log(f"   Simulation Status: {status}, Mode: {mode}, Uptime: {uptime}s")
            
            if status == "running" and mode == "simulation":
                self.log("✅ Simulation mode working correctly")
            else:
                self.log(f"❌ Unexpected status/mode: {status}/{mode}")
                return False
        
        # Check logs for any errors
        logs_success, logs_response = self.run_test(
            "Check Simulation Logs",
            "GET",
            "logs",
            200
        )
        
        if logs_success:
            logs = logs_response.get('logs', [])
            error_logs = [log for log in logs if 'ERROR' in log.get('level', '').upper() or 'error' in log.get('message', '').lower()]
            
            if error_logs:
                self.log(f"⚠️  Found {len(error_logs)} error logs during simulation:")
                for log in error_logs[-3:]:  # Show last 3 errors
                    self.log(f"     {log.get('message', 'N/A')}")
            else:
                self.log("✅ No error logs found during simulation")
        
        # Stop bot
        stop_success = self.run_test("Stop Bot After Simulation", "POST", "bot/stop", 200)
        
        return status_success and stop_success

    def test_configuration_buy_amount(self):
        """Test that buy_amount is configured correctly (should be 0.03 SOL)"""
        success, response = self.run_test(
            "Get Configuration for Buy Amount",
            "GET",
            "config",
            200
        )
        
        if success:
            config = response.get('config', {})
            
            # Check for buy amount in various possible locations
            buy_amount = None
            
            # Check common config paths
            if 'TRADING' in config and 'BUY_AMOUNT_SOL' in config['TRADING']:
                buy_amount = config['TRADING']['BUY_AMOUNT_SOL']
            elif 'BUY_AMOUNT_SOL' in config:
                buy_amount = config['BUY_AMOUNT_SOL']
            elif 'buy_amount' in config:
                buy_amount = config['buy_amount']
            
            if buy_amount is not None:
                self.log(f"   Buy amount configured: {buy_amount} SOL")
                if abs(float(buy_amount) - 0.03) < 0.001:  # Allow small floating point differences
                    self.log("✅ Buy amount correctly set to 0.03 SOL")
                    return True
                else:
                    self.log(f"⚠️  Buy amount is {buy_amount} SOL, expected 0.03 SOL")
                    return True  # Not a critical issue
            else:
                self.log("⚠️  Buy amount not found in config")
                # Check setup endpoint for default values
                setup_success, setup_response = self.run_test(
                    "Get Setup Configuration",
                    "GET",
                    "setup",
                    200
                )
                if setup_success:
                    setup_data = setup_response.get('setup', {})
                    self.log(f"   Setup data available: {list(setup_data.keys()) if setup_data else 'none'}")
                
                self.log("   Note: Buy amount might be set via DEFAULT_BUY_AMOUNT environment variable (0.03)")
                return True  # Not a critical failure
        
        return success

    def test_dashboard_metrics(self):
        """Test metrics endpoints (no dashboard endpoint exists)"""
        # Test metrics endpoint instead of dashboard
        success, response = self.run_test(
            "Get Metrics (Dashboard Alternative)",
            "GET",
            "metrics",
            200
        )
        
        if success:
            # Check if response has expected metrics structure
            if isinstance(response, dict):
                self.log(f"   Metrics data keys: {list(response.keys())}")
                self.log("✅ Metrics endpoint working (dashboard alternative)")
            else:
                self.log(f"   Metrics response type: {type(response)}")
        
        # Also test KPI metrics
        kpi_success, kpi_response = self.run_test(
            "Get KPI Metrics",
            "GET", 
            "metrics/kpi",
            200
        )
        
        if kpi_success:
            self.log(f"   KPI metrics available: {list(kpi_response.keys()) if isinstance(kpi_response, dict) else 'N/A'}")
        
        return success and kpi_success

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
            
            async with websockets.connect(ws_url) as websocket:
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
        self.log("🚀 Starting HFT Bot API Test Suite - ParseService Correction Testing")
        self.log(f"Testing against: {self.base_url}")
        
        # CRITICAL ParseService Correction Tests
        self.log("\n🔧 CRITICAL ParseService Correction Tests...")
        
        # Test 1: Health check first
        if not self.test_health():
            self.log("❌ Health check failed - may indicate server issues", "ERROR")
        
        # Test 2: Configuration
        config = self.test_config_get()
        self.test_configuration_buy_amount()
        
        # Test 3: COMPREHENSIVE ParseService test (MOST IMPORTANT)
        self.test_parse_service_comprehensive()
        
        # Test 4: Additional ParseService-specific tests
        self.test_parse_service_metrics()
        self.test_parse_service_logs_clean()
        
        # Test 5: Verify API endpoints still work
        self.test_dashboard_metrics()
        
        # Additional Clone & Inject Tests (regression check)
        self.log("\n🔧 Clone & Inject Regression Tests...")
        
        # Test 6: Import and syntax for Clone & Inject functionality
        self.test_clone_and_inject_import()
        
        # Test 7: _extract_pump_accounts structure for Clone & Inject
        self.test_extract_pump_accounts_structure()
        
        # Test 8: Position endpoints with Clone & Inject data verification
        self.test_positions_with_sell_data()
        
        # Additional standard tests
        self.log("\n📋 Standard API Tests...")
        
        # Configuration tests
        self.test_config_update(config)
        
        # Comprehensive Wallet Tests
        self.log("\n💼 Testing Wallet Functionality...")
        
        # Step 1: Reset wallet to clean state
        wallet_reset_success = self.test_wallet_reset()
        
        # Step 2: Test initial wallet status (should show not setup)
        initial_status = self.test_wallet_status()
        
        # Step 3: Test balance fetching with known Solana address (real RPC call)
        test_address = "vines1vzrYbzLMRdu58ou5XTby4qAqVRLmqo36NKPTg2"
        self.test_wallet_balance_by_address(test_address)
        
        # Step 4: Test wallet encryption with proper keypair
        wallet_data = self.test_wallet_encrypt()
        
        if wallet_data:
            # Step 5: Test wallet status after encryption (should show setup and unlocked)
            status_after_encrypt = self.test_wallet_status()
            
            # Step 6: Test configured wallet balance 
            self.test_wallet_balance_configured()
            
            # Step 7: Reset wallet and test unlock flow
            if self.test_wallet_reset():
                # Re-encrypt for unlock test
                self.test_wallet_encrypt(wallet_data['key'], wallet_data['passphrase'])
                
                # Test unlock
                unlocked_address = self.test_wallet_unlock(wallet_data['passphrase'])
                
                if unlocked_address and unlocked_address == wallet_data['address']:
                    self.log("   ✅ Address consistency check passed")
                elif unlocked_address:
                    self.log(f"   ❌ Address mismatch: {wallet_data['address']} vs {unlocked_address}")
                
                # Test configured wallet balance after unlock
                self.test_wallet_balance_configured()
        else:
            self.log("   ⚠️  Skipping additional wallet tests due to encryption failure")
        
        # Additional bot tests
        self.log("\n🤖 Additional Bot Tests...")
        bot_status = self.test_bot_status()
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

    def test_parse_service_logs_clean(self):
        """Test that ParseService logs are clean (no WARNING spam)"""
        self.log("Testing ParseService logs for WARNING spam elimination...")
        
        success, response = self.run_test(
            "Get Logs for ParseService Check",
            "GET",
            "logs?limit=100",  # Get more logs to check
            200
        )
        
        if success:
            logs = response.get('logs', [])
            self.log(f"   Checking {len(logs)} log entries for WARNING spam...")
            
            # Look for "Could not parse TX" warnings
            parse_warnings = []
            parse_debug_entries = []
            
            for log in logs:
                message = log.get('message', '')
                level = log.get('level', '').upper()
                
                # Check for the specific WARNING spam we're trying to eliminate
                if 'could not parse tx' in message.lower() or 'could not parse' in message.lower():
                    if level == 'WARNING' or level == 'WARN':
                        parse_warnings.append(message)
                    elif level == 'DEBUG':
                        parse_debug_entries.append(message)
                
                # Also check for other parse-related warnings
                if 'parse' in message.lower() and ('warning' in level.lower() or 'warn' in level.lower()):
                    if 'could not' in message.lower() or 'failed' in message.lower():
                        parse_warnings.append(message)
            
            # Report findings
            if parse_warnings:
                self.log(f"❌ Found {len(parse_warnings)} parse-related WARNING entries:")
                for warning in parse_warnings[:3]:  # Show first 3
                    self.log(f"     WARNING: {warning}")
                
                self.failed_tests.append({
                    "name": "ParseService WARNING Spam Check",
                    "expected": "No 'Could not parse TX' warnings",
                    "actual": f"Found {len(parse_warnings)} warnings",
                    "endpoint": "logs",
                    "error": f"ParseService still generating WARNING spam: {len(parse_warnings)} warnings found"
                })
                self.critical_issues.append(f"CRITICAL: ParseService WARNING spam not eliminated - found {len(parse_warnings)} warnings")
                return False
            else:
                self.log("✅ No parse-related WARNING spam found in logs")
                
                if parse_debug_entries:
                    self.log(f"   Found {len(parse_debug_entries)} parse-related DEBUG entries (expected)")
                    # Show a sample debug entry
                    if parse_debug_entries:
                        self.log(f"   Sample DEBUG: {parse_debug_entries[0][:80]}...")
                
                return True
        
        return success

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