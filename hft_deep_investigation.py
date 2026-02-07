#!/usr/bin/env python3

import requests
import json
import time
import sys
from datetime import datetime

class HFTDeepInvestigation:
    def __init__(self, base_url="https://trade-clone-25.preview.emergentagent.com"):
        self.base_url = base_url

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")

    def api_call(self, method, endpoint, data=None):
        """Make API call and return response"""
        url = f"{self.base_url}/api/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            
            return response.status_code, response.json() if response.text else {}
        except Exception as e:
            self.log(f"API call failed: {e}", "ERROR")
            return 0, {}

    def investigate_wallet_locked_behavior(self):
        """Deep investigation of wallet locked behavior"""
        self.log("\n🔍 DEEP INVESTIGATION: Wallet Locked Behavior")
        
        # Reset wallet to ensure locked state
        status, _ = self.api_call("POST", "wallet/reset")
        self.log(f"Wallet reset: {status}")
        
        # Verify wallet is locked
        status, response = self.api_call("GET", "wallet/status")
        if status == 200:
            is_unlocked = response.get('is_unlocked', True)
            is_setup = response.get('is_setup', True)
            self.log(f"Wallet state: setup={is_setup}, unlocked={is_unlocked}")
        
        # Set to live mode
        status, response = self.api_call("POST", "bot/toggle-mode")
        if status == 200:
            mode = response.get('mode', 'unknown')
            self.log(f"Mode set to: {mode}")
        
        # Start bot with locked wallet
        self.log("Starting bot with locked wallet...")
        status, response = self.api_call("POST", "bot/start")
        self.log(f"Bot start response: {response}")
        
        if status == 200:
            # Let bot run for 10 seconds to generate wallet locked events
            self.log("Letting bot run for 10 seconds to generate wallet locked events...")
            time.sleep(10)
            
            # Check bot status
            status, response = self.api_call("GET", "bot/status")
            if status == 200:
                bot_status = response.get('status', 'unknown')
                mode = response.get('mode', 'unknown')
                uptime = response.get('uptime_seconds', 0)
                self.log(f"Bot status after 10s: {bot_status}, mode: {mode}, uptime: {uptime}s")
                
                if bot_status == "running":
                    self.log("✅ Bot remains running with locked wallet (non-blocking)")
                else:
                    self.log(f"❌ Bot not running: {bot_status}")
            
            # Check logs for wallet locked events
            self.investigate_logs_for_wallet_events()
        
        # Stop bot
        self.api_call("POST", "bot/stop")

    def investigate_logs_for_wallet_events(self):
        """Look for wallet locked events in logs"""
        self.log("\n🔍 Investigating logs for wallet locked events...")
        
        status, response = self.api_call("GET", "logs?limit=100")
        if status == 200:
            logs = response.get('logs', [])
            
            wallet_events = []
            guard_events = []
            json_events = []
            
            for log in logs:
                message = log.get('message', '')
                level = log.get('level', '')
                timestamp = log.get('timestamp', '')
                
                # Check for JSON structured logs
                if message.startswith('{'):
                    try:
                        log_data = json.loads(message)
                        json_events.append(log_data)
                        
                        event_type = log_data.get('event', '')
                        if event_type == 'guard_drop':
                            guard_events.append(log_data)
                            reason = log_data.get('reason', '')
                            if reason == 'wallet_locked':
                                wallet_events.append(log_data)
                    except json.JSONDecodeError:
                        pass
                
                # Check for text-based wallet events
                if 'wallet' in message.lower() and 'locked' in message.lower():
                    wallet_events.append({'message': message, 'level': level, 'timestamp': timestamp})
            
            self.log(f"Total logs checked: {len(logs)}")
            self.log(f"JSON structured logs: {len(json_events)}")
            self.log(f"Guard drop events: {len(guard_events)}")
            self.log(f"Wallet locked events: {len(wallet_events)}")
            
            # Show sample events
            if wallet_events:
                self.log("Sample wallet locked events:")
                for i, event in enumerate(wallet_events[:3]):
                    if isinstance(event, dict) and 'reason' in event:
                        self.log(f"  {i+1}. JSON: {event}")
                    else:
                        self.log(f"  {i+1}. Text: {event.get('message', 'N/A')}")
            
            if guard_events:
                self.log("Sample guard drop events:")
                for i, event in enumerate(guard_events[:3]):
                    reason = event.get('reason', 'N/A')
                    sig = event.get('sig', 'N/A')
                    self.log(f"  {i+1}. Reason: {reason}, Sig: {sig[:16] if sig != 'N/A' else 'N/A'}...")

    def investigate_json_structured_logging(self):
        """Investigate JSON structured logging implementation"""
        self.log("\n🔍 DEEP INVESTIGATION: JSON Structured Logging")
        
        # Start bot to generate activity
        self.api_call("POST", "bot/stop")  # Ensure stopped
        time.sleep(1)
        
        # Set to simulation mode for predictable events
        status, response = self.api_call("POST", "bot/toggle-mode")
        if status == 200 and response.get('mode') == 'live':
            self.api_call("POST", "bot/toggle-mode")  # Toggle to simulation
        
        # Start bot
        status, response = self.api_call("POST", "bot/start")
        if status == 200:
            self.log("Bot started, letting it run for 15 seconds to generate events...")
            time.sleep(15)
            
            # Get logs
            status, response = self.api_call("GET", "logs?limit=150")
            if status == 200:
                logs = response.get('logs', [])
                
                json_logs = []
                event_types = {}
                parse_events = []
                
                for log in logs:
                    message = log.get('message', '')
                    
                    # Check for JSON structured logs
                    if message.startswith('{') and '"event":' in message:
                        try:
                            log_data = json.loads(message)
                            json_logs.append(log_data)
                            
                            event_type = log_data.get('event', 'unknown')
                            event_types[event_type] = event_types.get(event_type, 0) + 1
                            
                            # Collect parse-related events
                            if 'parse' in event_type:
                                parse_events.append(log_data)
                                
                        except json.JSONDecodeError:
                            pass
                
                self.log(f"Total logs: {len(logs)}")
                self.log(f"JSON structured logs: {len(json_logs)}")
                self.log(f"Event types found: {event_types}")
                self.log(f"Parse-related events: {len(parse_events)}")
                
                # Show sample JSON logs
                if json_logs:
                    self.log("\nSample JSON structured logs:")
                    for i, log_data in enumerate(json_logs[:5]):
                        event = log_data.get('event', 'N/A')
                        ts = log_data.get('ts', 'N/A')
                        self.log(f"  {i+1}. Event: {event}, TS: {ts}")
                        
                        # Show additional fields for specific events
                        if event == 'parse_drop':
                            reason = log_data.get('reason', 'N/A')
                            sig = log_data.get('sig', 'N/A')
                            self.log(f"      Reason: {reason}, Sig: {sig[:16] if sig != 'N/A' else 'N/A'}...")
                        elif event == 'candidate':
                            sig = log_data.get('sig', 'N/A')
                            source = log_data.get('source_wss_id', 'N/A')
                            self.log(f"      Sig: {sig[:16] if sig != 'N/A' else 'N/A'}..., Source: {source}")
                
                # Check for parse_drop_reason specifically
                parse_drop_reasons = {}
                for event in parse_events:
                    if event.get('event') == 'parse_drop':
                        reason = event.get('reason', 'unknown')
                        parse_drop_reasons[reason] = parse_drop_reasons.get(reason, 0) + 1
                
                if parse_drop_reasons:
                    self.log(f"\nParse drop reasons found: {parse_drop_reasons}")
                    self.log("✅ parse_drop_reason logging is working")
                else:
                    self.log("\n⚠️  No parse_drop events found (may be normal in simulation)")
        
        # Stop bot
        self.api_call("POST", "bot/stop")

    def investigate_metrics_implementation(self):
        """Investigate metrics for parse_dropped"""
        self.log("\n🔍 DEEP INVESTIGATION: Metrics Implementation")
        
        status, response = self.api_call("GET", "metrics")
        if status == 200:
            counters = response.get('counters', {})
            gauges = response.get('gauges', {})
            histograms = response.get('histograms', {})
            
            self.log(f"Available counters: {list(counters.keys())}")
            self.log(f"Available gauges: {list(gauges.keys())}")
            self.log(f"Available histograms: {list(histograms.keys())}")
            
            # Check for parse-related metrics
            parse_metrics = {k: v for k, v in counters.items() if 'parse' in k.lower()}
            self.log(f"Parse-related metrics: {parse_metrics}")
            
            # Check if parse_dropped exists
            if 'parse_dropped' in counters:
                self.log(f"✅ parse_dropped metric exists: {counters['parse_dropped']}")
            else:
                self.log("❌ parse_dropped metric missing")
                
                # Check for alternative names
                alternatives = ['parse_drop_expected', 'parse_failed', 'parse_drop']
                found_alternatives = {k: counters[k] for k in alternatives if k in counters}
                if found_alternatives:
                    self.log(f"Alternative parse drop metrics found: {found_alternatives}")

    def investigate_best_effort_parsing(self):
        """Investigate best-effort parsing implementation"""
        self.log("\n🔍 DEEP INVESTIGATION: Best-Effort Parsing (No Retries)")
        
        # Check parse service implementation by looking at metrics over time
        self.api_call("POST", "bot/stop")
        time.sleep(1)
        
        # Get baseline metrics
        status, response = self.api_call("GET", "metrics")
        baseline_metrics = response.get('counters', {}) if status == 200 else {}
        
        # Start bot in simulation mode
        self.api_call("POST", "bot/toggle-mode")  # Ensure simulation mode
        status, response = self.api_call("POST", "bot/start")
        
        if status == 200:
            self.log("Bot started, monitoring parse behavior for 20 seconds...")
            
            # Monitor metrics every 5 seconds
            for i in range(4):
                time.sleep(5)
                status, response = self.api_call("GET", "metrics")
                if status == 200:
                    current_metrics = response.get('counters', {})
                    
                    # Calculate changes
                    parse_attempts = current_metrics.get('parse_attempt', 0) - baseline_metrics.get('parse_attempt', 0)
                    parse_success = current_metrics.get('parse_success', 0) - baseline_metrics.get('parse_success', 0)
                    parse_drops = current_metrics.get('parse_drop_expected', 0) - baseline_metrics.get('parse_drop_expected', 0)
                    
                    self.log(f"  After {(i+1)*5}s: attempts=+{parse_attempts}, success=+{parse_success}, drops=+{parse_drops}")
            
            # Final metrics check
            status, response = self.api_call("GET", "metrics")
            if status == 200:
                final_metrics = response.get('counters', {})
                
                total_attempts = final_metrics.get('parse_attempt', 0) - baseline_metrics.get('parse_attempt', 0)
                total_success = final_metrics.get('parse_success', 0) - baseline_metrics.get('parse_success', 0)
                total_drops = final_metrics.get('parse_drop_expected', 0) - baseline_metrics.get('parse_drop_expected', 0)
                
                self.log(f"\nFinal results over 20s:")
                self.log(f"  Parse attempts: +{total_attempts}")
                self.log(f"  Parse success: +{total_success}")
                self.log(f"  Parse drops: +{total_drops}")
                
                if total_attempts > 0:
                    success_rate = (total_success / total_attempts) * 100
                    drop_rate = (total_drops / total_attempts) * 100
                    self.log(f"  Success rate: {success_rate:.1f}%")
                    self.log(f"  Drop rate: {drop_rate:.1f}%")
                    
                    if drop_rate > 0:
                        self.log("✅ Best-effort parsing with drops is working")
                    else:
                        self.log("⚠️  No drops observed (may be normal in simulation)")
                else:
                    self.log("⚠️  No parse attempts observed")
        
        # Stop bot
        self.api_call("POST", "bot/stop")

    def run_deep_investigation(self):
        """Run all deep investigations"""
        self.log("🔬 Starting Deep Investigation of HFT Bot Features")
        self.log("="*60)
        
        self.investigate_wallet_locked_behavior()
        self.investigate_json_structured_logging()
        self.investigate_metrics_implementation()
        self.investigate_best_effort_parsing()
        
        self.log("\n" + "="*60)
        self.log("🔬 Deep Investigation Complete")

def main():
    investigator = HFTDeepInvestigation()
    investigator.run_deep_investigation()

if __name__ == "__main__":
    main()