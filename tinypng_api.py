import requests
import os
import threading
from requests.adapters import HTTPAdapter
from logging_system import logger

try:
    from urllib3.util.retry import Retry
except ImportError:  # 兼容旧版 requests 内置的 urllib3
    from requests.packages.urllib3.util.retry import Retry


def _build_retry():
    kwargs = {
        'total': 2,
        'connect': 2,
        'read': 2,
        'backoff_factor': 0.5,
        'status_forcelist': (429, 500, 502, 503, 504),
        'raise_on_status': False,
    }
    try:
        return Retry(allowed_methods=frozenset(['GET', 'POST']), **kwargs)
    except TypeError:  # urllib3 < 1.26 使用旧参数名
        return Retry(method_whitelist=frozenset(['GET', 'POST']), **kwargs)


class TinyPNGAPI:
    API_URL = "https://api.tinify.com/shrink"

    # 按 API Key 复用 Session：省去每个任务重建连接的开销，并统一挂载有限重试。
    _sessions = {}
    _sessions_lock = threading.Lock()

    @classmethod
    def _get_session(cls, api_key):
        with cls._sessions_lock:
            session = cls._sessions.get(api_key)
            if session is None:
                session = requests.Session()
                session.auth = ('api', api_key)
                adapter = HTTPAdapter(max_retries=_build_retry(), pool_maxsize=4)
                session.mount('https://', adapter)
                cls._sessions[api_key] = session
            return session

    def __init__(self, api_key):
        self.api_key = api_key
        self.session = self._get_session(api_key)

    def compress_file(self, input_path, output_path, timeout=30):
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        original_size = os.path.getsize(input_path)
        shrink_response = None

        try:
            with open(input_path, 'rb') as f:
                shrink_response = self.session.post(
                    self.API_URL,
                    data=f,
                    timeout=timeout,
                    headers={'Content-Type': 'application/octet-stream'}
                )

            shrink_response.raise_for_status()

            if 'Location' in shrink_response.headers:
                download_url = shrink_response.headers['Location']
                download_response = self.session.get(download_url, timeout=timeout)
                download_response.raise_for_status()
                compressed_data = download_response.content
            else:
                compressed_data = shrink_response.content

            with open(output_path, 'wb') as f:
                f.write(compressed_data)

            compressed_size = len(compressed_data)

            return {
                'success': True,
                'original_size': original_size,
                'compressed_size': compressed_size,
                'ratio': 1 - (compressed_size / original_size) if original_size > 0 else 0,
                'compression_count': self._parse_compression_count(shrink_response)
            }

        except requests.exceptions.Timeout:
            logger.error(f"Compression timed out for: {input_path}")
            raise TimeoutError("Compression request timed out")

        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error for: {input_path}")
            raise ConnectionError("Network connection failed")

        except requests.exceptions.HTTPError as e:
            status_code = getattr(e.response, 'status_code', 0)
            error_message = f"HTTP error {status_code}"

            if status_code == 401:
                error_message = "Invalid API key"
            elif status_code == 429:
                error_message = "API rate limit exceeded"
            elif status_code == 400:
                error_message = "Invalid image file"
            elif status_code == 500:
                error_message = "Server error"

            logger.error(f"{error_message} for: {input_path}")
            raise Exception(error_message)

        except Exception as e:
            logger.error(f"Unexpected error compressing {input_path}: {str(e)}")
            raise

    @staticmethod
    def _parse_compression_count(response):
        """安全解析 Compression-Count 响应头（含 list/int/str 各种形态）。"""
        try:
            count_header = response.headers.get('Compression-Count', '0')
            if count_header is None:
                return 0
            if isinstance(count_header, list):
                count_header = count_header[0] if count_header else '0'
            if isinstance(count_header, int):
                return count_header
            count_str = str(count_header).strip()
            return int(count_str) if count_str.isdigit() else 0
        except Exception as e:
            logger.warning(f"Failed to parse Compression-Count header: {e}")
            return 0

    def validate_api_key(self):
        try:
            test_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9c\x03\x00\x01\x00\x01\x05\x00\x01\r\n~\x8b\x00\x00\x00\x00IEND\xaeB`\x82'
            
            response = self.session.post(
                self.API_URL,
                data=test_data,
                headers={'Content-Type': 'image/png'},
                timeout=10
            )
            
            if response.status_code == 400:
                return True
            elif response.status_code == 401:
                return False
            return False
        
        except Exception:
            return False