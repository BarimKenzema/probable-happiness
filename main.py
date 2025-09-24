# FINAL SCRIPT v46-STRUCTURAL-FILTER: Adds a pre-filter to discard structurally weak configs before testing.

import os, json, re, base64, time, traceback, socket
import requests
from urllib.parse import urlparse, parse_qs
import concurrent.futures

RUN_MODE = os.environ.get('RUN_MODE', 'LOCAL')
print(f"--- V2RAY REFINER v46-STRUCTURAL-FILTER --- RUNNING IN {RUN_MODE} MODE ---")

# --- CONFIGURATION ---
MAX_TEST_WORKERS = 100
TEST_TIMEOUT = 5

# --- NEW: Blacklists for the structural pre-filter ---
# We will discard configs whose SNI/Host matches these patterns.
# These are common, low-effort hostnames from free domains and cheap VPS providers.
SNI_BLACKLIST_PATTERNS = [
    ".cf", ".ga", ".gq", ".ml", ".tk", ".xyz", ".top", ".sbs", ".online", ".website",
    "speedtest", "vps", "server", "relay", "iran", "cloudfront.net"
]

# We will also discard configs using these common, easily detectable WebSocket paths.
WS_PATH_BLACKLIST = ["/", "/ws", "/v2ray", "/xray", "/trojan", "/vless", "/vmess"]

# --- THIS IS THE NEW PRE-FILTER FUNCTION ---
def structural_pre_filter(configs):
    """
    Inspects the config string itself to discard ones with obvious weaknesses
    BEFORE doing any time-consuming network tests.
    """
    print(f"--- Applying structural pre-filter to {len(configs)} configs... ---")
    high_quality_candidates = []
    for config in configs:
        try:
            # Rule 1: Always keep REALITY configs, they are structurally different.
            if 'reality' in config.lower():
                high_quality_candidates.append(config)
                continue

            parsed_url = urlparse(config)
            params = parse_qs(parsed_url.query)
            
            # Get SNI (from 'sni' or 'host' param) and the actual server address
            sni = params.get('sni', [params.get('host', [None])[0]])[0]
            host_address = parsed_url.hostname

            if not sni:
                sni = host_address # If no SNI is specified, the host address is used.

            # Rule 2: Check SNI against the blacklist.
            if any(pattern in sni.lower() for pattern in SNI_BLACKLIST_PATTERNS):
                continue # Discard if SNI is suspicious

            # Rule 3: For WebSocket configs, check the path.
            network_type = params.get('type', ['tcp'])[0].lower()
            if network_type == 'ws':
                ws_path = params.get('path', ['/'])[0]
                if ws_path in WS_PATH_BLACKLIST:
                    continue # Discard if WebSocket path is generic

            # If it passes all checks, it's a good candidate.
            high_quality_candidates.append(config)
        
        except Exception:
            continue
            
    print(f"--- Structural pre-filter complete. Kept {len(high_quality_candidates)} high-quality candidates for testing. ---")
    return high_quality_candidates

# --- TEST FUNCTION (Advanced Probe) ---
# This is now only run on the high-quality candidates.
def test_advanced_probe(config):
    try:
        parsed_url = urlparse(config); host = parsed_url.hostname; port = parsed_url.port or 443
        if not host: return None
        params = parse_qs(parsed_url.query); network_type = params.get('type', ['tcp'])[0].lower()
        requires_http_probe = network_type in ['ws', 'grpc']
        start_time = time.time()
        
        # We need a real DNS resolver for local testing
        from dns import resolver, exception as dns_exception
        try:
            res = resolver.Resolver(); res.nameservers = ["8.8.8.8", "1.1.1.1"]
            ips = [str(rdata) for rdata in res.resolve(host, 'A', raise_on_no_answer=False) or []]
            if not ips: return None
        except (dns_exception.DNSException, Exception): return None
        
        import ssl
        context = ssl.create_default_context(); context.check_hostname = False; context.verify_mode = ssl.CERT_NONE
        
        with socket.create_connection((ips[0], port), timeout=TEST_TIMEOUT) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                if requires_http_probe:
                    http_request = (f"GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\nUser-Agent: Mozilla/5.0\r\n\r\n")
                    ssock.sendall(http_request.encode('utf-8'))
                    response = ssock.recv(1024)
                    if not response: return None
                latency = int((time.time() - start_time) * 1000)
                return {"config": config, "latency": latency, "protocol": parsed_url.scheme}
    except Exception:
        return None

# =========================================================================================
# --- LOCAL MODE ---
# This is the only mode that matters now, as GitHub mode is too simple.
# This script is now purely for local execution.
# =========================================================================================
def run_local_mode():
    def setup_directories():
        import shutil
        dirs = ['./subscribe']
        for d in dirs:
            if os.path.exists(d): shutil.rmtree(d)
            os.makedirs(d)

    def write_subscription_file(filepath, configs):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        content = base64.b64encode("\n".join(configs).encode("utf-8")).decode("utf-8")
        with open(filepath, "w", encoding="utf-8") as f: f.write(content)

    setup_directories()
    
    # We now go back to reading the big list from Repo A.
    # The structural pre-filter is so good, we don't need the intermediate GitHub step.
    SOURCE_URL = "https://raw.githubusercontent.com/BarimKenzema/Haj-Karim/main/filtered-for-refiner.txt"
    try:
        print(f"Downloading full list from {SOURCE_URL}")
        response = requests.get(SOURCE_URL, timeout=30)
        response.raise_for_status()
        initial_configs = list(set(line.strip() for line in response.text.splitlines() if line.strip()))
        print(f"Successfully loaded {len(initial_configs)} configs from Stage 1.")
    except Exception as e:
        print(f"FATAL: Could not download configs from Repo A. Error: {e}"); return

    # --- APPLY THE NEW PRE-FILTER FIRST ---
    configs_to_test = structural_pre_filter(initial_configs)
    
    if not configs_to_test: print("FATAL: No configs survived the structural pre-filter."); return
    
    print(f"\n--- Running Network Tests on {len(configs_to_test)} candidates ---")
    good_configs_data = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_TEST_WORKERS) as executor:
        f_to_c = {executor.submit(test_advanced_probe, c): c for c in configs_to_test}
        for i, f in enumerate(concurrent.futures.as_completed(f_to_c)):
            if (i + 1) % 50 == 0: print(f"Tested {i+1}/{len(configs_to_test)} | Found {len(good_configs_data)} working")
            result = f.result()
            if result: good_configs_data.append(result)

    good_configs_data.sort(key=lambda x: (x['protocol'] != 'reality', x['latency']))
    print(f"--- Found {len(good_configs_data)} VERIFIED high-quality configs. ---")
    if not good_configs_data: return

    # Titling and writing the final file
    final_configs_titled = []
    for item in good_configs_data:
        try:
            # We don't need geoip for this simplified version, just latency
            host = urlparse(item['config']).hostname
            clean_config = item['config'].split('#')[0]
            title = f"L{item['latency']}ms-{host}"
            final_configs_titled.append(f"{clean_config}#{title}")
        except: continue
        
    if final_configs_titled:
        write_subscription_file('./subscribe/verified_all', final_configs_titled)
        print(f"Final subscription file created at './subscribe/verified_all'")

# --- MAIN ENTRY POINT ---
if __name__ == "__main__":
    # We are simplifying back to a single, powerful local script.
    # The dual-mode complexity is not needed if the pre-filter is effective.
    run_local_mode()