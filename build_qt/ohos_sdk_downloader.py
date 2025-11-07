"""
OpenHarmony SDK 下载器

提供 OhosSdkDownloader 类：
- get_sdk_list(os_type, os_arch, support_version): 请求 SDK 列表
- parse_download_links(sdk_list, components=None): 解析并返回组件到下载 URL 的映射
- download_component(url, dest_path, expected_checksum=None, chunk_size=8192): 下载并校验 sha256
- download_component_by_name(api_version, component_name, os_type, os_arch, support_version, dest_dir): 高层 API，指定 apiVersion 和组件名称下载

设计原则：模块化、易于测试、清晰的异常与日志输出
"""
from __future__ import annotations

import os
import requests
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .utils import download_component

class DownloadError(Exception):
    pass

@dataclass
class ComponentArchive(object):
    def __init__(self, url: Tuple[str, str], size: int = None, checksum: str = None, os_arch: str = None):
        self.url = url
        self.size = size
        self.checksum = checksum
        self.os_arch = os_arch


class OhosSdkDownloader:
    """OpenHarmony SDK 下载器。

    Example:
        downloader = OhosSdkDownloader(os_type='windows', os_arch='x64', support_version='6.0-ohos-single-2')
        sdk_list = downloader.get_sdk_list()
        links = downloader.parse_download_links(sdk_list)
        downloader.download_component(links['native'], 'C:/tmp/native.zip', expected_checksum=None)
    """

    def __init__(self, url: Tuple[str, str], os_type: str, os_arch: str, support_version: str, timeout: int = 30):
        self.url = url
        self.session = requests.Session()
        self.timeout = timeout
        self.os_type = os_type
        self.os_arch = os_arch
        self.support_version = support_version

    def build_request_body(self) -> Dict:
        return {
            'osArch': self.os_arch,
            'osType': self.os_type,
            'supportVersion': self.support_version,
        }

    def get_sdk_list(self) -> List[Dict]:
        """从远程获取 SDK 列表，返回 JSON 列表结构。

        Raises:
            DownloadError: 网络或解析错误时抛出
        """
        body = self.build_request_body()
        try:
            resp = self.session.post(self.url[0], json=body, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                raise DownloadError('Unexpected response format: expected a list')
            return data
        except requests.RequestException as e:
            raise DownloadError('Failed to fetch SDK list: {}'.format(e))
        except ValueError as e:
            raise DownloadError('Failed to parse JSON: {}'.format(e))

    def get_backup_sdk_list(self) -> List[Dict]:
        """从备用 URL 获取 SDK 列表，返回 JSON 列表结构。

        Raises:
            DownloadError: 网络或解析错误时抛出
        """
        body = self.build_request_body()
        try:
            resp = self.session.get(self.url[1] + '-{}'.format(self.os_type), timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                raise DownloadError('Unexpected response format: expected a list')
            return data
        except requests.RequestException as e:
            raise DownloadError('Failed to fetch backup SDK list: {}'.format(e))
        except ValueError as e:
            raise DownloadError('Failed to parse JSON from backup: {}'.format(e))

    def get_supported_versions(self) -> List[str]:
        """获取支持的 apiVersion 列表。

        Raises:
            DownloadError: 网络或解析错误时抛出
        """
        sdk_list = self.get_sdk_list()
        backup_sdk_list = self.get_backup_sdk_list()
        versions = set()
        for entry in sdk_list:
            sv = entry.get('apiVersion')
            if sv:
                versions.add(sv)
        for entry in backup_sdk_list:
            sv = entry.get('apiVersion')
            if sv:
                versions.add(sv)
        return sorted(versions)

    @staticmethod
    def parse_download_links(sdk_list: Iterable[Dict], components: Optional[Iterable[str]] = None) -> Dict[str, ComponentArchive]:
        """解析 SDK 列表，返回组件名 -> ComponentArchive 映射。

        If components is provided, only returns those components.
        """
        comp_set = set(components) if components is not None else None
        result = {}
        for entry in sdk_list:
            path = entry.get('path')
            if not path:
                continue
            if comp_set is not None and path not in comp_set:
                continue
            archive = entry.get('archive') or {}
            url = archive.get('url')
            size = archive.get('size')
            checksum = archive.get('checksum')
            os_arch = archive.get('osArch')
            if url:
                try:
                    size_int = int(size) if size is not None else None
                except (ValueError, TypeError):
                    size_int = None
                result[path] = ComponentArchive(url=url, size=size_int, checksum=checksum, os_arch=os_arch)
        return result

    def download_component_by_name(self, api_version: str, component_name: str, dest_dir: str) -> str:
        """高层 API：请求 SDK 列表并下载指定 apiVersion 和组件名的组件。

        - api_version: apiVersion 字符串（例如 '20'）用于匹配 entry['apiVersion']
        - component_name: 组件名称，如 'native'、'js'、'ets'、'previewer'、'toolchains'
        - os_type/os_arch/support_version: 请求参数
        - dest_dir: 保存目录

        Returns 保存的文件路径
        """
        sdk_list = self.get_sdk_list()
        backup_sdk_list = self.get_backup_sdk_list()
        # filter by apiVersion then by path
        matches = [e for e in sdk_list if str(e.get('apiVersion')) == str(api_version) and e.get('path') == component_name]
        if not matches:
            matches = [e for e in backup_sdk_list if str(e.get('apiVersion')) == str(api_version) and e.get('path') == component_name]
        if not matches:
            raise DownloadError('No matching component found for apiVersion={}, component={}'.format(api_version, component_name))
        entry = matches[0]
        archive = entry.get('archive') or {}
        url = archive.get('url')
        checksum = ('sha256', archive.get('checksum'))
        if not url:
            raise DownloadError('No download URL found in archive')
        file_name = os.path.basename(url.split('?')[0])
        dest_path = os.path.join(dest_dir, file_name)
        print(url)
        saved_path = download_component(url=url, dest_path=dest_path, expected_checksum=checksum)
        return saved_path

    


