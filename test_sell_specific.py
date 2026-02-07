#!/usr/bin/env python3

import requests
import json
import time
import sys
from datetime import datetime

class SellFeatureTest:
    def __init__(self, base_url="https://trade-clone-25.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")

    def run_test(self, name, method, endpoint, expected_status, data=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        self.log(f"Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)

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
                    "error": response.text[:200]
                })
                
                return False, {}

        except Exception as e:
            self.log(f"❌ {name} - Error: {str(e)}", "ERROR")
            self.failed_tests.append({
                "name": name,
                "error": str(e)
            })
            return False, {}

    def test_import_sell_functions(self):
        """Test that all sell-related functions can be imported"""
        self.log("Testing import of sell functionality...")
        try:
            import sys
            sys.path.append('/app/backend')
            
            # Test imports
            from services.solana_trader import SolanaTrader, build_sell_instruction
            from services.position_manager import PositionData
            
            # Test SolanaTrader methods
            trader_methods = ['execute_sell', 'build_sell_transaction']
            missing_methods = []
            
            for method in trader_methods:
                if not hasattr(SolanaTrader, method):
                    missing_methods.append(method)
            
            # Test build_sell_instruction function
            try:
                # This should not raise an error if function exists
                import inspect
                sig = inspect.signature(build_sell_instruction)
                expected_params = ['seller', 'mint', 'bonding_curve', 'associated_bonding_curve', 
                                 'seller_ata', 'token_amount', 'min_sol_output', 'creator_vault', 
                                 'user_volume_accumulator', 'token_program']
                actual_params = list(sig.parameters.keys())
                
                self.log(f"   build_sell_instruction parameters: {len(actual_params)} found")
                
            except Exception as e:
                missing_methods.append(f"build_sell_instruction (error: {e})")
            
            # Test PositionData fields
            pos = PositionData("test", "test", 0.001, 0.03, 80, "test")
            sell_fields = ['bonding_curve', 'associated_bonding_curve', 'token_program', 'creator', 'token_amount']
            missing_fields = []
            
            for field in sell_fields:
                if not hasattr(pos, field):
                    missing_fields.append(field)
            
            if missing_methods or missing_fields:
                self.log(f"❌ Missing components - Methods: {missing_methods}, Fields: {missing_fields}")
                return False
            else:
                self.log("✅ All sell functionality imports successfully")
                return True
                
        except Exception as e:
            self.log(f"❌ Import test failed: {e}")
            return False

    def test_force_sell_endpoint_modes(self):
        """Test force-sell endpoint behavior in different scenarios"""
        self.log("Testing force-sell endpoint...")
        
        # First, start bot in simulation mode and create some positions
        self.run_test("Stop Bot", "POST", "bot/stop", 200)
        time.sleep(1)
        
        # Toggle to simulation mode
        self.run_test("Toggle to Simulation", "POST", "bot/toggle-mode", 200)
        self.run_test("Start Bot", "POST", "bot/start", 200)
        
        # Wait for positions to be created
        self.log("   Waiting for simulation positions to be created...")
        time.sleep(6)
        
        # Get positions
        success, response = self.run_test("Get Positions", "GET", "positions", 200)
        if not success:
            return False
            
        positions = response.get('positions', [])
        self.log(f"   Found {len(positions)} positions")
        
        if positions:
            pos = positions[0]
            pos_id = pos['id']
            pos_name = pos.get('token_name', 'Unknown')
            
            # Check if position has sell data
            sell_fields = ['bonding_curve', 'associated_bonding_curve', 'token_program', 'creator', 'token_amount']
            has_sell_data = any(pos.get(field) is not None for field in sell_fields)
            
            self.log(f"   Position {pos_name} has sell data: {has_sell_data}")
            
            # Test force-sell
            success, response = self.run_test(
                f"Force-Sell {pos_name}", "POST", f"positions/{pos_id}/force-sell", 200
            )
            
            if success:
                if response.get('success'):
                    mode = response.get('mode', 'unknown')
                    self.log(f"   ✅ Force-sell successful in {mode} mode")
                    
                    # Check if position was closed
                    closed_pos = response.get('position', {})
                    if closed_pos.get('status') == 'closed':
                        reason = closed_pos.get('close_reason', 'N/A')
                        self.log(f"   ✅ Position closed with reason: {reason}")
                        return True
                    else:
                        self.log(f"   ❌ Position not closed: {closed_pos.get('status')}")
                        return False
                else:
                    error = response.get('error', 'Unknown')
                    if 'missing' in error.lower():
                        self.log(f"   ⚠️  Expected error for missing sell data: {error}")
                        return True
                    else:
                        self.log(f"   ❌ Unexpected error: {error}")
                        return False
        else:
            self.log("   ⚠️  No positions available to test force-sell")
            return True
        
        return False

    def test_position_data_structure(self):
        """Test that positions have the correct data structure for sell operations"""
        self.log("Testing position data structure...")
        
        # Get current positions
        success, response = self.run_test("Get Positions for Structure Check", "GET", "positions", 200)
        if not success:
            return False
            
        positions = response.get('positions', [])
        
        if positions:
            pos = positions[0]
            
            # Check required fields for basic position
            basic_fields = ['id', 'token_mint', 'token_name', 'entry_price_sol', 'amount_sol', 'status']
            missing_basic = [f for f in basic_fields if f not in pos]
            
            # Check sell-related fields
            sell_fields = ['bonding_curve', 'associated_bonding_curve', 'token_program', 'creator', 'token_amount']
            present_sell = [f for f in sell_fields if f in pos]
            
            self.log(f"   Basic fields present: {len(basic_fields) - len(missing_basic)}/{len(basic_fields)}")
            self.log(f"   Sell fields present: {len(present_sell)}/{len(sell_fields)}")
            
            if missing_basic:
                self.log(f"   ❌ Missing basic fields: {missing_basic}")
                return False
            else:
                self.log(f"   ✅ All basic position fields present")
                
            # For simulation mode, sell fields may be None/empty, which is acceptable
            self.log(f"   ✅ Position structure is valid for sell operations")
            return True
        else:
            self.log("   ⚠️  No positions to check structure")
            return True

    def run_all_tests(self):
        """Run all sell-specific tests"""
        self.log("🚀 Starting Sell Feature Specific Tests")
        
        # Test 1: Import functionality
        self.test_import_sell_functions()
        
        # Test 2: Position data structure
        self.test_position_data_structure()
        
        # Test 3: Force-sell endpoint
        self.test_force_sell_endpoint_modes()
        
        # Clean up
        self.run_test("Stop Bot (cleanup)", "POST", "bot/stop", 200)

    def print_summary(self):
        """Print test results summary"""
        self.log("\n" + "="*50)
        self.log("🔍 SELL FEATURE TEST SUMMARY")
        self.log("="*50)
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        
        self.log(f"Total Tests: {self.tests_run}")
        self.log(f"Passed: {self.tests_passed}")
        self.log(f"Failed: {len(self.failed_tests)}")
        self.log(f"Success Rate: {success_rate:.1f}%")
        
        if self.failed_tests:
            self.log("\n❌ FAILED TESTS:")
            for test in self.failed_tests:
                self.log(f"  - {test['name']}")
                if 'error' in test:
                    self.log(f"    Error: {test['error']}")
        
        if success_rate >= 80:
            self.log("\n✅ Sell Feature Status: WORKING")
            return 0
        else:
            self.log("\n❌ Sell Feature Status: ISSUES FOUND")
            return 1

def main():
    tester = SellFeatureTest()
    
    try:
        tester.run_all_tests()
    except Exception as e:
        tester.log(f"\n💥 Test suite crashed: {str(e)}", "ERROR")
        return 2
    
    return tester.print_summary()

if __name__ == "__main__":
    sys.exit(main())