# FILE: main.py (for your SECOND repo: v2ray-refiner)
# FINAL SCRIPT v42: Advanced Refiner with "All-In-One" File Output

import os, json, re, base64, time, traceback, socket, ssl
import requests
from urllib.parse import urlparse, parse_qs
import concurrent.futures
import geoip2.database
from dns import resolver, exception as dns_exception

print("--- ADVANCED REFINER v42 (ALL-IN-ONE OUTPUT) START ---")

# --- CONFIGURATION ---
CONFIG_CHUNK_SIZE = 999
MAX_TEST_WORKERS = 100
TEST_TIMEOUT = 4
SMALL_COUNTRY_THRESHOLD = 44
HISTORY_DB_FILE = "server_history.json"
BANNED_ASNS = {
    "AS15169", "AS16509", "AS8075", "AS14618", "AS20473", "AS24940", "AS14061"
} # Google, AWS, Azure, DigitalOcean, Vultr, Hetzner, Linode

# --- HELPER FUNCTIONS ---
def setup_directories():
    import shutil
    dirs = ['./splitted', './subscribe', './protocols', './networks', './countries']
    for d in dirs:
        if os.path.exists(d): shutil.rmtree(d)
        os.makedirs(d)
    print("INFO: All necessary directories are clean.")

dns_cache = {}
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

cdn_cache = {}
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

def load_history():
    try:
        with open(HISTORY_DB_FILE, 'r') as f: return json.load(f)
    except: return {}

def save_history(history):
    with open(HISTORY_DB_FILE, 'w') as f: json.dump(history, f, indent=2)

def advanced_test_single_config(config, asn_reader):
    try:
        parsed_url = urlparse(config); host = parsed_url.hostname; port = parsed_url.port or 443
        if not host: return None
        
        start_time = time.time()
        context = ssl.create_default_context(); context.check_hostname = False; context.verify_mode = ssl.CERT_NONE
        
        with socket.create_connection((host, port), timeout=TEST_TIMEOUT) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                pass
        
        latency = int((time.time() - start_time) * 1000)
        
        if asn_reader:
            ips = get_ips(host)
            if not ips: return None
            try:
                asn_record = asn_reader.asn(ips[0])
                asn = f"AS{asn_record.autonomous_system_number}"
                if asn in BANNED_ASNS: return None
            except geoip2.errors.AddressNotFoundError: pass
            except Exception: return None

        with socket.create_connection((host, port), timeout=TEST_TIMEOUT) as plain_sock:
            http_request = f"GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode()
            plain_sock.sendall(http_request)
            response = plain_sock.recv(1024).decode('utf-8', 'ignore')
            if not response.lower().startswith("http/1."): return None

        return {
            "config": config, "host": host, "latency": latency,
            "is_cdn": is_cdn_domain(host),
            "is_reality": 'reality' in config.lower(),
        }
    except Exception: return None

def run_advanced_tests(configs_to_test, asn_reader):
    print(f"\n--- Running Advanced Tests on {len(configs_to_test)} configs... ---")
    good_configs_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_TEST_WORKERS) as executor:
        future_to_config = {executor.submit(advanced_test_single_config, config, asn_reader): config for config in configs_to_test}
        for i, future in enumerate(concurrent.futures.as_completed(future_to_config)):
            if (i + 1) % 100 == 0: print(f"Tested {i+1}/{len(configs_to_test)} | Found: {len(good_configs_results)}")
            result = future.result()
            if result: good_configs_results.append(result)
    print(f"--- Advanced testing complete. Found {len(good_configs_results)} high-quality configs. ---")
    return good_configs_results

def process_and_title_configs(configs, geoip_reader):
    processed_configs = []; print(f"\n--- Adding Geo-Titles to {len(configs)} configs... ---")
    for element in configs:
        try:
            host = urlparse(element).hostname; ips = get_ips(host)
            if not host or not ips: continue
            country_code = "XX"
            if geoip_reader:
                try: country_code = geoip_reader.country(ips[0]).country.iso_code or "XX"
                except geoip2.errors.AddressNotFoundError: pass
            processed_configs.append(urlparse(element)._replace(fragment=f"#{country_code}-{host}").geturl())
        except Exception: continue
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

def main():
    setup_directories()
    
    REFINER_SOURCE_URL = "https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/v2ray-collector/main/filtered-for-refiner.txt"
    try:
        response = requests.get(REFINER_SOURCE_URL, timeout=20)
        response.raise_for_status()
        configs_to_test = {line.strip() for line in response.text.splitlines() if line.strip()}
        print(f"Successfully collected {len(configs_to_test)} pre-filtered configs to test.")
    except Exception as e:
        print(f"FATAL: Could not download configs from the collector repo. Error: {e}"); return
    if not configs_to_test: print("FATAL: Config source file was empty. Exiting."); return

    history = load_history()
    configs_to_test_list = sorted(list(configs_to_test), key=lambda c: history.get(urlparse(c).hostname, {}).get('success_streak', 0), reverse=True)

    country_db_path = "./geoip-country.mmdb"; asn_db_path = "./geoip-asn.mmdb"
    try:
        if not os.path.exists(country_db_path):
            r = requests.get("https://git.io/GeoLite2-Country.mmdb", allow_redirects=True); r.raise_for_status()
            with open(country_db_path, 'wb') as f: f.write(r.content)
        if not os.path.exists(asn_db_path):
            r = requests.get("https://git.io/GeoLite2-ASN.mmdb", allow_redirects=True); r.raise_for_status()
            with open(asn_db_path, 'wb') as f: f.write(r.content)
        country_reader = geoip2.database.Reader(country_db_path)
        asn_reader = geoip2.database.Reader(asn_db_path)
    except Exception as e:
        print(f"ERROR: Could not download/load GeoIP databases. Some features disabled. Error: {e}")
        country_reader, asn_reader = None, None

    good_configs_results = run_advanced_tests(configs_to_test_list, asn_reader)
    if not good_configs_results: print("INFO: No high-quality configs found. Exiting."); return

    successful_hosts = {res['host'] for res in good_configs_results}
    for host, data in history.items():
        if host in successful_hosts: data['success_streak'] = data.get('success_streak', 0) + 1; data['failures'] = 0
        else: data['success_streak'] = 0; data['failures'] = data.get('failures', 0) + 1
    for res in good_configs_results:
        if res['host'] not in history: history[res['host']] = {'success_streak': 1, 'failures': 0}
    save_history(history)

    good_configs_results.sort(key=lambda r: (history.get(r['host'], {}).get('success_streak', 0), -r['is_cdn'], -r['is_reality'], r['latency']), reverse=True)
    final_configs_sorted = [res['config'] for res in good_configs_results]
    
    final_configs_titled = process_and_title_configs(final_configs_sorted, country_reader)
    
    by_protocol = {p: [] for p in ["vless", "vmess", "trojan", "ss", "reality"]}
    by_country = {}
    for config in final_configs_titled:
        try:
            proto = config.split('://')[0]
            if proto in by_protocol: by_protocol[proto].append(config)
            if 'reality' in config.lower(): by_protocol['reality'].append(config)
            country_code = urlparse(config).fragment.split('-')[0].lower()
            if country_code:
                if country_code not in by_country: by_country[country_code] = []
                by_country[country_code].append(config)
        except Exception: continue
    
    for p, clist in by_protocol.items(): write_chunked_subscription_files(f'./protocols/{p}', clist)
    for c, clist in by_country.items(): write_chunked_subscription_files(f'./countries/{c}', clist)

    print(f"\n--- Creating Special Combined Subscription File ---")
    combined_configs = set()
    if by_protocol['reality']: combined_configs.update(by_protocol['reality'])
    if 'tr' in by_country: combined_configs.update(by_country['tr'])
    for country_code, config_list in by_country.items():
        if len(config_list) < SMALL_COUNTRY_THRESHOLD: combined_configs.update(config_list)
    
    if combined_configs:
        final_combined_list = sorted(list(combined_configs), key=lambda c: final_configs_titled.index(c))
        print(f"Total unique configs in the special combined file: {len(final_combined_list)}")
        write_chunked_subscription_files('./subscribe/combined_special', final_combined_list)

    # --- NEW: Write all high-quality configs to a single file ---
    print("\n--- Writing ALL refined configs to a single subscription file ---")
    write_chunked_subscription_files('./subscribe/all_refined', final_configs_titled)

    print("\n--- SCRIPT FINISHED SUCCESSFULLY ---")

if __name__ == "__main__":
    try: main()
    except Exception: print(f"\n--- FATAL UNHANDLED ERROR ---"); traceback.print_exc(); exit(1)
