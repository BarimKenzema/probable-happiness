# FILE: main.py (for your SECOND repo: v2ray-refiner)
# FINAL SCRIPT v40: Refiner with Corrected Combined Logic

import os, json, re, base64, time, traceback, socket
import requests
from urllib.parse import urlparse, parse_qs
import concurrent.futures
import geoip2.database
from dns import resolver, exception as dns_exception
import ssl

print("--- ADVANCED REFINER & CATEGORIZER v40 START ---")

# --- CONFIGURATION ---
CONFIG_CHUNK_SIZE = 444
MAX_TEST_WORKERS = 100
TEST_TIMEOUT = 4
SMALL_COUNTRY_THRESHOLD = 44

# --- HELPER FUNCTIONS (UNCHANGED) ---
def setup_directories():
    import shutil
    dirs = ['./splitted', './subscribe', './protocols', './networks', './countries']
    for d in dirs:
        if os.path.exists(d): shutil.rmtree(d)
        os.makedirs(d)
    print("INFO: All necessary directories are clean.")

dns_cache = {}
cdn_cache = {}

def get_ips(node):
    if node in dns_cache: return dns_cache[node]
    try:
        import ipaddress
        if ipaddress.ip_address(node):
            dns_cache[node] = [node]; return [node]
    except ValueError:
        try:
            res = resolver.Resolver(); res.nameservers = ["8.8.8.8", "1.1.1.1"]
            ips = [str(rdata) for rdata in res.resolve(node, 'A', raise_on_no_answer=False) or []]
            if ips: dns_cache[node] = ips; return ips
        except (dns_exception.DNSException, Exception): return None
    return None

def is_cdn_domain(domain):
    if domain in cdn_cache: return cdn_cache[domain]
    try:
        res = resolver.Resolver(); res.nameservers = ["1.1.1.1", "8.8.8.8"]
        parts = domain.split('.'); base_domain = '.'.join(parts[-2:]) if len(parts) > 1 else domain
        ns_records = res.resolve(base_domain, 'NS')
        for record in ns_records:
            if 'cloudflare.com' in str(record).lower():
                cdn_cache[domain] = True; return True
    except (dns_exception.DNSException, Exception): pass
    cdn_cache[domain] = False; return False

def test_single_config(config):
    try:
        parsed_url = urlparse(config); host = parsed_url.hostname; port = parsed_url.port or 443
        if not host: return None
        is_cdn = is_cdn_domain(host)
        start_time = time.time()
        context = ssl.create_default_context(); context.check_hostname = False; context.verify_mode = ssl.CERT_NONE
        with socket.create_connection((host, port), timeout=TEST_TIMEOUT) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                latency = int((time.time() - start_time) * 1000)
                return {"config": config, "host": host, "latency": latency, "is_cdn": is_cdn, "protocol": parsed_url.scheme}
    except (socket.timeout, ConnectionRefusedError, OSError, ssl.SSLError, Exception): return None

def advanced_filter_and_test(all_configs):
    print(f"\n--- Advanced Filtering & Testing {len(all_configs)} Pre-Filtered Configs ---")
    unique_configs = list(set(all_configs)); good_configs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_TEST_WORKERS) as executor:
        future_to_config = {executor.submit(test_single_config, config): config for config in unique_configs}
        for i, future in enumerate(concurrent.futures.as_completed(future_to_config)):
            if (i + 1) % 500 == 0: print(f"Tested {i+1}/{len(unique_configs)} | Promising: {len(good_configs)}")
            result = future.result()
            if result: good_configs.append(result)
    good_configs.sort(key=lambda x: (not x['is_cdn'], x['protocol'] != 'reality', x['latency']))
    final_sorted_configs = [item['config'] for item in good_configs]
    print(f"--- Advanced filtering complete. Found {len(final_sorted_configs)} high-quality configs. ---")
    return final_sorted_configs

def process_and_title_configs(configs_to_process, geoip_reader):
    print(f"\n--- Adding Geo-Titles to {len(configs_to_process)} configs... ---"); processed_configs = []
    for element in configs_to_process:
        try:
            host = urlparse(element).hostname; ips = get_ips(host)
            if not host or not ips: continue
            country_code = "XX"
            if geoip_reader:
                try: country_code = geoip_reader.country(ips[0]).country.iso_code or "XX"
                except geoip2.errors.AddressNotFoundError: pass
            clean_config = element.split('#')[0]; title = f"{country_code}-{host}"
            processed_configs.append(f"{clean_config}#{title}")
        except Exception: continue
    print(f"--- Finished titling. Final count: {len(processed_configs)} ---")
    return processed_configs

def write_chunked_subscription_files(base_filepath, configs):
    os.makedirs(os.path.dirname(base_filepath), exist_ok=True)
    if not configs:
        with open(base_filepath, "w") as f: f.write(""); return
    chunks = [configs[i:i + CONFIG_CHUNK_SIZE] for i in range(0, len(configs), CONFIG_CHUNK_SIZE)]
    for i, chunk in enumerate(chunks):
        filename = os.path.basename(base_filepath)
        filepath = base_filepath if i == 0 else os.path.join(os.path.dirname(base_filepath), f"{filename}{i + 1}")
        content = base64.b64encode("\n".join(chunk).encode("utf-8")).decode("utf-8")
        with open(filepath, "w", encoding="utf-8") as f: f.write(content)

# --- MAIN EXECUTION ---
def main():
    setup_directories()
    
    # --- Stage 1: Download pre-filtered configs from Repo A ---
    # !!! IMPORTANT: CHANGE 'YOUR_GITHUB_USERNAME' and 'v2ray-collector' !!!
    REFINER_SOURCE_URL = "https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/v2ray-collector/main/filtered-for-refiner.txt"
    
    print(f"--- Downloading PRE-FILTERED configs from collector: {REFINER_SOURCE_URL} ---")
    configs_to_test = set()
    try:
        response = requests.get(REFINER_SOURCE_URL, timeout=20)
        response.raise_for_status()
        configs_text = response.text
        configs_to_test.update(line.strip() for line in configs_text.splitlines() if line.strip())
        print(f"Successfully collected {len(configs_to_test)} pre-filtered configs to test.")
    except requests.exceptions.RequestException as e:
        print(f"FATAL: Could not download configs from the collector repo. Error: {e}"); return

    if not configs_to_test: print("FATAL: Config source file was empty. Exiting."); return

    # --- Stage 2: Run advanced tests and add geo-titles ---
    db_path = "./geoip.mmdb"
    if not os.path.exists(db_path):
        print("INFO: GeoIP database not found. Downloading...")
        try:
            r = requests.get("https://git.io/GeoLite2-Country.mmdb", allow_redirects=True)
            with open(db_path, 'wb') as f: f.write(r.content)
            print("INFO: GeoIP database downloaded successfully.")
        except Exception as e: print(f"ERROR: Could not download GeoIP database. Error: {e}"); db_path = None
    
    high_quality_configs = advanced_filter_and_test(list(configs_to_test))
    if not high_quality_configs: print("INFO: No high-quality configs found after advanced testing. Exiting."); return
    
    geoip_reader = None
    if db_path and os.path.exists(db_path):
        try: geoip_reader = geoip2.database.Reader(db_path)
        except Exception as e: print(f"ERROR: Could not load GeoIP database. Error: {e}")

    final_configs = process_and_title_configs(high_quality_configs, geoip_reader)

    # --- Stage 3: Perform standard categorization ---
    print("\n--- Performing Standard Categorization ---")
    by_protocol = {p: [] for p in ["vless", "vmess", "trojan", "ss", "reality"]}
    by_network = {'tcp': [], 'ws': [], 'grpc': []}
    by_country = {}

    for config in final_configs:
        try:
            proto = config.split('://')[0]
            if proto in by_protocol: by_protocol[proto].append(config)
            if 'reality' in config.lower(): by_protocol['reality'].append(config)
            
            parsed = urlparse(config)
            net = parse_qs(parsed.query).get('type', ['tcp'])[0].lower()
            if net in by_network: by_network[net].append(config)
            
            country_code = parsed.fragment.split('-')[0].lower()
            if country_code:
                if country_code not in by_country: by_country[country_code] = []
                by_country[country_code].append(config)
        except Exception: continue

    # Write standard category files for general use
    for p, clist in by_protocol.items(): write_chunked_subscription_files(f'./protocols/{p}', clist)
    for n, clist in by_network.items(): write_chunked_subscription_files(f'./networks/{n}', clist)
    for c, clist in by_country.items(): write_chunked_subscription_files(f'./countries/{c}', clist)

    # --- Stage 4: Create Special Combined Subscription (UPDATED LOGIC) ---
    print(f"\n--- Creating Special Combined Subscription File ---")
    
    # Use a set to automatically handle duplicates
    combined_configs = set()

    # 1. Add ALL REALITY servers
    if by_protocol['reality']:
        print(f"Adding {len(by_protocol['reality'])} REALITY configs to the special mix.")
        combined_configs.update(by_protocol['reality'])
    
    # 2. Add ALL Turkey servers
    if 'tr' in by_country:
        print(f"Adding {len(by_country['tr'])} Turkey (TR) configs to the special mix.")
        combined_configs.update(by_country['tr'])

    # 3. Add all servers from countries with fewer than 44 configs
    for country_code, config_list in by_country.items():
        if len(config_list) < SMALL_COUNTRY_THRESHOLD:
            print(f"Adding {len(config_list)} configs from small country '{country_code.upper()}' to the special mix.")
            combined_configs.update(config_list)
    
    if combined_configs:
        # Convert set to a sorted list for consistent output
        final_combined_list = sorted(list(combined_configs))
        print(f"Total unique configs in the special combined file: {len(final_combined_list)}")
        write_chunked_subscription_files('./subscribe/combined_special', final_combined_list)
    else:
        print("No configs met the criteria for the special combined subscription.")

    print("\n--- SCRIPT FINISHED SUCCESSFULLY ---")

if __name__ == "__main__":
    try: main()
    except Exception: print(f"\n--- FATAL UNHANDLED ERROR IN MAIN ---"); traceback.print_exc(); exit(1)
