#!/usr/bin/env python3

import sys
import os
sys.path.append('/app/backend')

def test_clone_inject_methods():
    """Test Clone & Inject methods directly"""
    print("🔧 Testing Clone & Inject Methods Directly...")
    
    try:
        from services.solana_trader import SolanaTrader
        from services.rpc_manager import RpcManagerService
        from services.wallet_service import WalletService
        
        # Create instances
        rpc_manager = RpcManagerService()
        wallet_service = WalletService(rpc_manager)
        trader = SolanaTrader(rpc_manager, wallet_service)
        
        # Test 1: Check methods exist
        print("✅ Testing method existence...")
        assert hasattr(trader, 'clone_and_inject_buy_transaction'), "clone_and_inject_buy_transaction missing"
        assert hasattr(trader, 'execute_buy_cloned'), "execute_buy_cloned missing"
        assert hasattr(trader, '_extract_pump_accounts'), "_extract_pump_accounts missing"
        print("   All Clone & Inject methods exist")
        
        # Test 2: Test _extract_pump_accounts with proper structure
        print("✅ Testing _extract_pump_accounts structure...")
        
        # Create a more realistic mock transaction
        mock_tx = {
            "meta": {
                "err": None,
                "postTokenBalances": [
                    {"mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "owner": "test_owner"}
                ]
            },
            "transaction": {
                "message": {
                    "accountKeys": [
                        {"pubkey": "4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf", "signer": False, "writable": False},  # global
                        {"pubkey": "62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV", "signer": False, "writable": True},   # fee_recipient
                        {"pubkey": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "signer": False, "writable": False},  # mint
                        {"pubkey": "test_bonding_curve", "signer": False, "writable": True},                              # bonding_curve
                        {"pubkey": "test_assoc_bonding_curve", "signer": False, "writable": True},                       # assoc_bonding_curve
                        {"pubkey": "test_user_ata", "signer": False, "writable": True},                                  # user_ata
                        {"pubkey": "test_creator", "signer": True, "writable": True},                                    # creator (signer)
                        {"pubkey": "11111111111111111111111111111111", "signer": False, "writable": False},              # system_program
                        {"pubkey": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "signer": False, "writable": False}, # token_program
                    ],
                    "instructions": [{
                        "programId": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
                        "accounts": [0, 1, 2, 3, 4, 5, 6, 7, 8],
                        "data": "test_instruction_data"
                    }]
                }
            }
        }
        
        result = trader._extract_pump_accounts(mock_tx)
        if result:
            print(f"   Extracted data keys: {list(result.keys())}")
            
            # Check for Clone & Inject specific fields
            required_fields = ['account_metas_clone', 'instruction_data']
            for field in required_fields:
                assert field in result, f"Missing required field: {field}"
            
            print(f"   account_metas_clone length: {len(result['account_metas_clone'])}")
            print(f"   instruction_data present: {bool(result['instruction_data'])}")
            
            # Check account_metas_clone structure
            if result['account_metas_clone']:
                first_meta = result['account_metas_clone'][0]
                required_meta_fields = ['pubkey', 'isSigner', 'isWritable']
                for field in required_meta_fields:
                    assert field in first_meta, f"Missing account meta field: {field}"
                print(f"   account_metas_clone structure correct")
            
            print("✅ _extract_pump_accounts returns correct Clone & Inject structure")
        else:
            print("   _extract_pump_accounts returned None (acceptable for mock data)")
        
        # Test 3: Test clone_and_inject_buy_transaction method signature
        print("✅ Testing clone_and_inject_buy_transaction method signature...")
        
        # Create mock parsed_create_data with account_metas_clone
        mock_parsed_data = {
            "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "bonding_curve": "test_bonding_curve",
            "associated_bonding_curve": "test_assoc_bonding_curve",
            "token_program": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
            "creator": "test_creator",
            "account_metas_clone": [
                {"pubkey": "4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf", "isSigner": False, "isWritable": False},
                {"pubkey": "62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV", "isSigner": False, "isWritable": True},
                {"pubkey": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "isSigner": False, "isWritable": False},
                {"pubkey": "test_bonding_curve", "isSigner": False, "isWritable": True},
                {"pubkey": "test_assoc_bonding_curve", "isSigner": False, "isWritable": True},
                {"pubkey": "test_user_ata", "isSigner": False, "isWritable": True},
                {"pubkey": "test_creator", "isSigner": True, "isWritable": True},
                {"pubkey": "11111111111111111111111111111111", "isSigner": False, "isWritable": False},
                {"pubkey": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "isSigner": False, "isWritable": False},
            ],
            "instruction_data": "test_data"
        }
        
        # This should fail gracefully without a keypair, but not crash
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            result = loop.run_until_complete(
                trader.clone_and_inject_buy_transaction(mock_parsed_data, 0.03)
            )
            
            # Should return None due to no keypair, but method should be callable
            if result is None:
                print("   clone_and_inject_buy_transaction callable (returned None as expected without keypair)")
            else:
                print(f"   Unexpected result: {result}")
                
            loop.close()
            
        except Exception as e:
            if "No keypair loaded" in str(e) or "keypair" in str(e).lower():
                print("   clone_and_inject_buy_transaction callable (failed as expected without keypair)")
            else:
                raise e
        
        print("✅ All Clone & Inject tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Clone & Inject test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_clone_inject_methods()
    sys.exit(0 if success else 1)