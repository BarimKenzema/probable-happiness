# FINAL SCRIPT v45-DUAL-CAT: Categorizes on both GitHub and Local with distinct filenames

import os, json, re, base64, time, traceback, socket
import requests
from urllib.parse import urlparse, parse_qs
import concurrent.futures
import geoip2.database
from dns import resolver, exception as dns_exception
import ssl

RUN_MODE = os.environ.get('RUN_MODE', 'LOCAL')
print(f"--- V2RAY REFINER v45-DUAL-CAT --- RUNNING IN {RUN_MODE} MODE ---")

# --- CONFIGURATION ---
CONFIG_CHUNK_SIZE = 4444
MAX_TEST_WORKERS = 100
TEST_TIMEOUT = 5
SMALL_COUNTRY_THRESHOLD = 44

# --- TEST FUNCTIONS ---
def test_simple_tls(config):
    try:
        parsed_url = urlparse(config); host = parsed_url.hostname; port = parsed_url.port or 443
        if not host: return None
        context = ssl.create_default_context(); context.check_hostname = False; context.verify_mode = ssl.CERT_NONE
        with socket.create_connection((host, port), timeout=3) as sock:
            with context.wrap_socket(sock, server_hostname=host):
                return config
    except Exception:
        return None

def test_advanced_probe(config):
    try:
        parsed_url = urlparse(config); host = parsed_url.hostname; port = parsed_url.port or 443
        if not host: return None
        params = parse_qs(parsed_url.query); network_type = params.get('type', ['tcp'])[0].lower()
        requires_http_probe = network_type in ['ws', 'grpc']
        start_time = time.time()
        context = ssl.create_default_context(); context.check_hostname = False; context.verify_mode = ssl.CERT_NONE
        ips = get_ips(host)
        if not ips: return None
        with socket.create_connection((ips[0], port), timeout=TEST_TIMEOUT) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                if requires_http_probe:
                    http_request = (f"GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\nUser-Agent: Mozilla/5.0\r\n\r\n")
                    ssock.sendall(http_request.encode('utf-8'))
                    response = ssock.recv(1024)
                    if not response: return None
                latency = int((time.time() - start_time) * 1000)
                return {"config": config, "host": host, "latency": latency, "protocol": parsed_url.scheme}
    except Exception:
        return None

# --- SHARED HELPER FUNCTIONS ---
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

def setup_directories():
    import shutil
    dirs = ['./splitted', './subscribe', './protocols', './countries']
    for d in dirs:
        if os.path.exists(d): shutil.rmtree(d)
        os.makedirs(d)

def write_subscription_file(filepath, configs):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    content = base64.b64encode("\n".join(configs).encode("utf-8")).decode("utf-8")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

# --- NEW SHARED CATEGORIZATION FUNCTION ---
def categorize_and_write_files(final_configs, geoip_reader, file_prefix="", file_suffix=""):
    """Categorizes a list of configs and writes them to files with given pre/suffixes."""
    print(f"\n--- Performing Categorization for {file_prefix or 'Local'}{file_suffix or ''} files ---")
    
    # Title the configs first
    titled_configs = []
    for config_str in final_configs:
        try:
            host = urlparse(config_str).hostname
            ips = get_ips(host)
            if not host or not ips: continue
            country_code = "XX"
            if geoip_reader:
                try: country_code = geoip_reader.country(ips[0]).country.iso_code or "XX"
                except geoip2.errors.AddressNotFoundError: pass
            clean_config = config_str.split('#')[0]
            title = f"{country_code}-{host}"
            titled_configs.append(f"{clean_config}#{title}")
        except Exception: continue

    if not titled_configs:
        print("No configs to categorize.")
        return

    # Create the main all-in-one file
    all_filename = f"./subscribe/{file_prefix}all{file_suffix}"
    print(f"Creating main subscription file: {all_filename}")
    write_subscription_file(all_filename, titled_configs)
    
    # Perform categorization
    by_protocol = {p: [] for p in ["vless", "vmess", "trojan", "ss", "reality"]}
    by_country = {}
    for config in titled_configs:
        try:
            proto = config.split('://')[0]
            if proto in by_protocol: by_protocol[proto].append(config)
            if 'reality' in config.lower(): by_protocol['reality'].append(config)
            country_code = urlparse(config).fragment.split('-')[0].lower()
            if country_code:
                if country_code not in by_country: by_country[country_code] = []
                by_country[country_code].append(config)
        except Exception: continue
    
    # Create the special combined file
    combined_configs = set()
    if by_protocol['reality']: combined_configs.update(by_protocol['reality'])
    if 'tr' in by_country: combined_configs.update(by_country['tr'])
    if 'ir' in by_country: combined_configs.update(by_country['ir'])
    for country_code, config_list in by_country.items():
        if len(config_list) < SMALL_COUNTRY_THRESHOLD: combined_configs.update(config_list)
    
    if combined_configs:
        combined_filename = f'./subscribe/{file_prefix}combined_special{file_suffix}'
        print(f"Creating special combined file: {combined_filename}")
        write_subscription_file(combined_filename, sorted(list(combined_configs)))

# =========================================================================================
# --- GITHUB MODE ---
# =========================================================================================
def run_github_mode():
    SOURCE_URL = "https://raw.githubusercontent.com/BarimKenzema/Haj-Karim/main/filtered-for-refiner.txt"
    try:
        response = requests.get(SOURCE_URL, timeout=30); response.raise_for_status()
        configs_to_test = list(set(line.strip() for line in response.text.splitlines() if line.strip()))
        print(f"Successfully loaded {len(configs_to_test)} configs from Stage 1.")
    except Exception as e:
        print(f"FATAL: Could not download configs from Repo A. Error: {e}"); return

    good_configs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_TEST_WORKERS) as executor:
        f_to_c = {executor.submit(test_simple_tls, c): c for c in configs_to_test}
        for i, f in enumerate(concurrent.futures.as_completed(f_to_c)):
            if (i + 1) % 500 == 0: print(f"Tested {i+1}/{len(configs_to_test)} | Found: {len(good_configs)}")
            if f.result(): good_configs.append(f.result())

    OUTPUT_FILE = "github-refined-list.txt"
    print(f"Found {len(good_configs)} promising configs. Saving to {OUTPUT_FILE}")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for config in good_configs: f.write(config + '\n')
    
    # --- New Categorization Step for GitHub ---
    if good_configs:
        setup_directories() # Clean old directories
        db_path = "./geoip.mmdb"; geoip_reader = None
        if not os.path.exists(db_path):
            try:
                r = requests.get("https://git.io/GeoLite2-Country.mmdb", allow_redirects=True)
                with open(db_path, 'wb') as f: f.write(r.content)
            except Exception: db_path = None
        if db_path:
            try: geoip_reader = geoip2.database.Reader(db_path)
            except Exception: pass
        categorize_and_write_files(good_configs, geoip_reader, file_prefix="github_")
    
    print("--- GITHUB MODE FINISHED SUCCESSFULLY ---")

# =========================================================================================
# --- LOCAL MODE ---
# =========================================================================================
def run_local_mode():
    LOCAL_SOURCE_FILE = "github-refined-list.txt"
    try:
        with open(LOCAL_SOURCE_FILE, 'r', encoding='utf-8') as f:
            configs_to_test = list(set(line.strip() for line in f if line.strip()))
        print(f"Successfully loaded {len(configs_to_test)} configs from Stage 2.")
    except FileNotFoundError:
        print(f"FATAL: Source file '{LOCAL_SOURCE_FILE}' not found. Run `local_runner.py` to sync."); return

    if not configs_to_test: print("FATAL: Config source file was empty."); return
    
    good_configs_data = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_TEST_WORKERS) as executor:
        f_to_c = {executor.submit(test_advanced_probe, c): c for c in configs_to_test}
        for i, f in enumerate(concurrent.futures.as_completed(f_to_c)):
            if (i + 1) % 100 == 0: print(f"Tested {i+1}/{len(configs_to_test)} | Found {len(good_configs_data)} high-quality configs")
            if f.result(): good_configs_data.append(f.result())

    good_configs_data.sort(key=lambda x: (x['protocol'] != 'reality', x['latency']))
    print(f"Found {len(good_configs_data)} high-quality configs.")
    if not good_configs_data: print("INFO: No configs found after advanced testing."); return
    
    # --- Categorization Step for Local ---
    setup_directories()
    db_path = "./geoip.mmdb"; geoip_reader = None
    if os.path.exists(db_path):
        try: geoip_reader = geoip2.database.Reader(db_path)
        except Exception: pass
    
    # We pass the raw config strings to the shared function
    raw_configs = [item['config'] for item in good_configs_data]
    categorize_and_write_files(raw_configs, geoip_reader, file_suffix="_verified")

    print("\n--- LOCAL MODE FINISHED SUCCESSFULLY ---")

# --- MAIN ENTRY POINT ---
if __name__ == "__main__":
    if RUN_MODE == 'GITHUB':
        run_github_mode()
    else:
        run_local_mode()
