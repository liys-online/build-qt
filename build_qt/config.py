
import json
import questionary
import os
import sys
from typing import Dict, Tuple
import platform
import subprocess
from build_qt.utils import detect_platform, download_component, extract_archive
from build_qt.ohos_sdk_downloader import OhosSdkDownloader

class Config:
    config = None
    user_config = None
    def __init__(self, config_path: str, use_gh: bool = False):
        self.root_path = os.path.abspath(os.path.dirname(config_path))
        self.use_gh = use_gh

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.system = platform.system()
        self.make_tools = 'mingw32-make' if self.system == 'Windows' else 'make'
        plat = detect_platform()
        self.ohos_sdk_downloader = OhosSdkDownloader(url=self.ohos_sdk_list_url(),
                                                     os_type=plat['osType'],
                                                     os_arch=plat['osArch'],
                                                     support_version=self.ohos_support_version())
        if sys.stdout.isatty():
            self.init_user_config()
        # else:
        #     self.save_usr_config(self.get_config())
        user_config_path = os.path.join(self.root_path, 'configure.json.user')
        with open(user_config_path, 'r', encoding='utf-8') as f:
            self.user_config = json.load(f)
        self.perl_path = self.get_build_tool_path('perl')
        self.mingw_path = self.get_build_tool_path('mingw')
        self.openssl_path = self.get_path('openssl')
        self.ohos_sdk_path = self.get_path('ohos_sdk')


    def init_user_config(self):
        user_config_path = os.path.join(self.root_path, 'configure.json.user')
        if not os.path.isfile(user_config_path):
            questionary.print('用户配置文件 {} 不存在，开始配置。'.format(user_config_path), style='bold fg:ansiyellow')
            answers = questionary.prompt([
                {
                    'type': 'path',
                    'name': 'working_dir',
                    'message': '请输入工作目录：',
                    'default': self.get_working_dir(),
                },
                {
                    'type': 'path',
                    'name': 'perl',
                    'message': '请配置perl路径（默认则自动下载）：',
                    'default': lambda the_answers: os.path.join(the_answers['working_dir'], 'perl')
                                if 'working_dir' in the_answers else self.get_build_tool_path('perl'),
                    'when': platform.system() != 'Windows'
                },
                {
                    'type': 'path',
                    'name': 'mingw',
                    'message': '请配置mingw路径（默认则自动下载）：',
                    'default': lambda the_answers: os.path.join(the_answers['working_dir'], 'mingw')
                                if 'working_dir' in the_answers else self.get_build_tool_path('mingw'),
                    'when': platform.system() != 'Windows'
                },
                {
                    'type': 'select',
                    'name': 'ohos_version',
                    'message': '请选择OpenHarmony SDK版本：',
                    'choices': self.ohos_sdk_downloader.get_supported_versions(),
                    'default': str(self.ohos_version())
                },
                {
                    'type': 'path',
                    'name': 'ohos_sdk',
                    'message': '请配置OpenHarmony SDK路径（默认则自动下载）：',
                    'default': lambda the_answers: os.path.join(the_answers['working_dir'], 'ohos_sdk', the_answers['ohos_version'])
                                if 'working_dir' in the_answers and 'ohos_version' in the_answers else self.get_path('ohos_sdk')
                },
                {
                    'type': 'select',
                    'name': 'build_qt_tag',
                    'message': '请选择要编译的 Qt 版本：',
                    'choices': self.supported_qt_tags(),
                    'default': self.tag()
                },
                {
                    'type': 'select',
                    'name': 'build_type',
                    'message': '请选择构建类型（Release/Debug）：',
                    'choices': ['release', 'debug'],
                    'default': self.build_type()
                },
                {
                    'type': 'select',
                    'name': 'build_ohos_abi',
                    'message': '请选择OpenHarmony目标架构：',
                    'choices': ['arm64-v8a', 'armeabi-v7a', 'x86-64'],
                    'default': self.build_ohos_abi()
                },
                {
                    'type': 'text',
                    'name': 'clone_depth',
                    'message': '请输入克隆深度（建议值1，0为完整克隆）：',
                    'default': str(self.clone_depth()),
                },
                {
                    'type': 'text',
                    'name': 'jobs',
                    'message': '请输入编译并行任务数（建议值为CPU核心数）：',
                    'default': str(self.build_jobs()),
                }
            ])
            print('用户配置：', answers)
            if answers == {}:
                print('用户取消操作，程序退出。')
                exit()   # 手动退出
            else:
                self.save_usr_config(answers)
                print('用户配置已保存到 {}'.format(user_config_path))

    def dev_env_check(self):
        need_perl = True
        need_mingw = True
        need_ohos_sdk = True
        need_openssl = self.openssl_runtime()
        if self.system == 'Windows':
            os.environ['PATH'] = ('C:\\Windows\\System32'
                                  + os.pathsep + 'C:\\Windows'
                                  + os.pathsep + os.path.dirname(sys.executable))
            if self.perl_path and os.path.isdir(self.perl_path):
                cmd = [os.path.join(self.perl_path, 'perl'), '-e', 'print sprintf("%vd",$^V);']
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode == 0:
                        print('perl 版本信息 {}'.format(result.stdout.strip()))
                        os.environ['PATH'] = os.environ.get('PATH', '') + os.pathsep + self.perl_path
                        need_perl = False
                except Exception as e:
                    print('执行 {} 失败：{}'.format(cmd, e))
            if self.mingw_path and os.path.isdir(self.mingw_path):
                cmd = [os.path.join(self.mingw_path, self.make_tools), '--version']
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode == 0:
                        print('{} 版本信息 {}'.format(self.make_tools, result.stdout[0:result.stdout.find('\n')].strip()))
                        os.environ['PATH'] = os.environ.get('PATH', '') + os.pathsep + self.mingw_path
                        need_mingw = False
                except Exception as e:
                    print('执行 {} 失败：{}'.format(cmd, e))
        else:
            cmd = None
            try:
                cmd = ['perl', '-e', 'print sprintf("%vd",$^V);']
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    print('perl 版本信息')
                    print(result.stdout)
                    need_perl = False
                cmd = [self.make_tools, '--version']
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    print('{} 版本信息'.format(self.make_tools))
                    print(result.stdout)
                    need_mingw = False
            except Exception as e:
                print('执行 {} 失败：{}'.format(cmd, e))

                if self.system == 'Linux':
                    print('请执行 sudo apt-get update && sudo apt-get install build-essential 以安装编译工具')
                if self.system == 'Darwin':
                    print('请从 App Store 安装最新的 Xcode 以安装编译工具')
                exit(1)
        if need_openssl and self.openssl_path and os.path.isdir(self.openssl_path):
            print('检测到 OpenSSL 路径 {}'.format(self.openssl_path))
            need_openssl = False
        if self.ohos_sdk_path and os.path.isdir(self.ohos_sdk_path):
            # 检查 native\oh-uni-package.json 是否存在
            package_json_path = os.path.join(self.ohos_sdk_path, 'native', 'oh-uni-package.json')
            if os.path.isfile(package_json_path):
                # 尝试读取 JSON 文件，检查是否能正确解析
                try:
                    with open(package_json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        print('OHOS SDK 版本信息 {}  {}'.format(data.get('apiVersion'), data.get('version')))
                        os.environ['OHOS_SDK_PATH'] = self.ohos_sdk_path
                        need_ohos_sdk = False
                except Exception as e:
                    print('警告: 无法解析 {}，文件可能损坏或格式不正确。错误: {}'.format(package_json_path, e))
        temp_dir = os.path.join(self.get_working_dir(), '.temp')
        if need_perl and self.system == 'Windows':
            depends_perl = self.get_depends().get('perl')
            perl_url = depends_perl.get('gh_url') if self.use_gh else depends_perl.get('gc_url')
            perl_checksum = ('sha256', self.get_depends().get('perl').get('sha256'))
            download_path = os.path.join(temp_dir, 'perl5.7z')
            print('正在下载并安装 Perl...')
            zip_path = download_component(perl_url, download_path, perl_checksum)
            perl_extracted_path = os.path.join(self.get_working_dir(), 'perl')
            extract_archive(zip_path, perl_extracted_path)
            if os.path.isdir(perl_extracted_path):
                self.perl_path = os.path.join(perl_extracted_path, 'bin')

        if need_mingw and self.system == 'Windows':
            depends_mingw = self.get_depends().get('mingw')
            mingw_url = depends_mingw.get('gh_url') if self.use_gh else depends_mingw.get('gc_url')
            mingw_checksum = ('sha256', depends_mingw.get('sha256'))
            download_path = os.path.join(temp_dir, 'mingw64-x86_64-8.1.0-release-posix-seh-rt_v6-rev0.7z')
            print('正在下载并安装 MinGW...')
            zip_path = download_component(mingw_url, download_path, mingw_checksum)
            mingw_extracted_path = os.path.join(self.get_working_dir(), 'mingw')
            extract_archive(zip_path, mingw_extracted_path)
            if os.path.isdir(mingw_extracted_path):
                self.mingw_path = os.path.join(mingw_extracted_path, 'bin')

        if need_openssl:
            depends_openssl = self.get_depends().get('openssl')
            openssl_url = depends_openssl.get('gh_url') if self.use_gh else depends_openssl.get('gc_url')
            openssl_checksum = ('sha256', self.get_depends().get('openssl').get('sha256'))
            download_path = os.path.join(temp_dir, 'openssl_1_1_1u.zip')
            print('正在下载并安装 OpenSSL...')
            tar_path = download_component(openssl_url, download_path, openssl_checksum)
            openssl_extracted_path = os.path.join(self.get_working_dir(), 'openssl')
            extract_archive(tar_path, openssl_extracted_path)
            if os.path.isdir(openssl_extracted_path):
                self.openssl_path = os.path.join(openssl_extracted_path, self.build_ohos_abi())

        if need_ohos_sdk:
            api_version = self.ohos_version()
            print('正在下载并安装 OpenHarmony SDK...')
            saved = self.ohos_sdk_downloader.download_component_by_name(api_version=api_version,
                                                                        component_name='native',
                                                                        dest_dir=temp_dir)
            extract_archive(saved, self.ohos_sdk_path)

        if need_perl or need_mingw or need_ohos_sdk:
            self.dev_env_check()

    def get_working_dir(self):
        working_dir = self.get_config_value('working_dir')
        if '${pwd}' in working_dir:
            working_dir = working_dir.replace('${pwd}', self.root_path)
        working_dir = os.path.abspath(os.path.expanduser(working_dir))
        return working_dir

    def get_output_path(self):
        return os.path.join(self.get_working_dir(), 'output')

    def replace_config_keys(self, old_str: str):
        config_keys = self.get_user_config().keys()
        if '${pwd}' in old_str:
            old_str = old_str.replace('${pwd}', self.root_path)
        old_str = os.path.abspath(os.path.expanduser(old_str))
        for key in config_keys:
            pattern = '${{{}}}'.format(key)
            if pattern in old_str:
                old_str = old_str.replace(pattern, str(self.get_config_value(key)))
        return old_str

    def get_path(self, tool_name: str):
        path = self.get_config_value(tool_name)
        return self.replace_config_keys(path)

    def get_build_tool_path(self, tool_name: str):
        tool_path = self.get_path(tool_name)
        # 判断是否有bin目录
        bin_dir = os.path.join(tool_path, 'bin')
        return bin_dir if os.path.isdir(bin_dir) else tool_path

    def ohos_sdk_list_url(self) -> Tuple[str, str]:
        back_url = 'gh_url' if self.use_gh else 'gc_url'
        return self.get_depends().get('ohos_sdk').get('url'), self.get_depends().get('ohos_sdk').get(back_url)

    def ohos_support_version(self):
        return self.get_depends().get('ohos_sdk').get('support_version')

    def supported_qt_tags(self):
        return self.config.get('supported-qt-tags')

    def ohos_version(self):
        return self.get_config_value('ohos_version')
    
    def qt_repo(self):
        _qt_repo = self.get_repos().get('qt_repo')
        return _qt_repo.get('gh_url') if self.use_gh else _qt_repo.get('gc_url')

    def qt_ohos_patch_repo(self):
        _qt_ohos_patch = self.get_repos().get('qt-ohos-patch')
        return _qt_ohos_patch.get('gh_url') if self.use_gh else _qt_ohos_patch.get('gc_url')
    
    def is_qt6(self):
        """判断当前是否为Qt6版本"""
        tag = self.tag()
        return tag.startswith('v6.')
    
    def tag(self):
        return self.get_config_value('build_qt_tag')

    def ohqt_tag(self):
        return self.get_config_value('build_ohqt_tag')

    def qt_version(self):
        return self.tag().replace('v', '').replace('-lts-lgpl', '')

    def build_type(self):
        return self.get_config_value('build_type')

    def build_prefix(self):
        return os.path.join(self.get_output_path(), 'Qt{}-ohos{}-{}'.format(self.qt_version(),
                                                                            self.ohos_version(),
                                                                            self.build_ohos_abi()))
    
    def build_host_prefix(self):
        """Qt6主机编译的安装路径"""
        return os.path.join(self.get_output_path(), 'Qt{}-host'.format(self.qt_version()))

    def build_ohos_abi(self):
        return self.get_config_value('build_ohos_abi')

    def clone_depth(self):
        return int(self.get_config_value('clone_depth'))

    def build_jobs(self):
        jobs = int(self.get_config_value('jobs'))
        if jobs <= os.cpu_count():
            return jobs
        return os.cpu_count()

    def openssl_runtime(self):
        """检查当前版本是否启用 OpenSSL 运行时支持"""
        tag = self.tag()
        
        # 根据 Qt 版本判断从哪个配置中读取
        if tag.startswith('v5.'):
            # Qt5 从 qt5-config[tag] 读取
            qt5_config = self.config.get('qt5-config', {})
            tag_options = qt5_config.get(tag, {})
            return tag_options.get('openssl-runtime', False)
        elif tag.startswith('v6.'):
            # Qt6 从 qt6-cross-config[tag] 读取（交叉编译才需要 OpenSSL）
            qt6_cross_config = self.config.get('qt6-cross-config', {})
            tag_options = qt6_cross_config.get(tag, {})
            return tag_options.get('openssl-runtime', False)
        
        return False

    def get_repos(self):
        return self.config.get('repositories', {})

    def get_depends(self):
        return self.config.get('dependencies', {})

    def get_config(self):
        return self.config.get('config')

    def get_user_config(self):
        if self.user_config is None:
            return self.get_config()
        return self.user_config.get('config', self.get_config())

    def get_config_value(self, key):
        return self.get_user_config().get(key, self.get_config().get(key))

    def save_usr_config(self, usr_config: Dict):
        usr_config_path = os.path.join(self.root_path, 'configure.json.user')
        obj = {
            'config': usr_config
        }
        with open(usr_config_path, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=4)

    def build_configure_options(self):
        """Qt5 的配置选项（从 qt5-config[tag] 读取）"""
        # 从 qt5-config 中获取当前版本的配置
        qt5_config = self.config.get('qt5-config', {})
        tag_options = qt5_config.get(self.tag(), {})
        
        if not tag_options:
            raise ValueError(f'配置文件中未找到Qt5版本 {self.tag()} 的配置')
        
        result = []
        
        # 基本选项（从父级获取）
        if qt5_config.get('license') in ['opensource', 'commercial']:
            result.append('-{}'.format(qt5_config['license']))
        if qt5_config.get('confirm-license'):
            result.append('-confirm-license')
        
        # 平台配置
        host_platform = 'win32-g++'
        if platform.system() == 'Linux':
            host_platform = 'linux-g++'
        elif platform.system() == 'Darwin':
            host_platform = 'macx-clang'
        result += ['-platform', host_platform]
        
        # 交叉编译平台
        if '-xplatform' in tag_options:
            result += ['-xplatform', tag_options['-xplatform']]
        
        # OpenGL 配置
        if '-opengl' in tag_options:
            result += ['-opengl', tag_options['-opengl']]
        if tag_options.get('-opengles3'):
            result.append('-opengles3')
        
        # DBus 配置
        if tag_options.get('-no-dbus'):
            result.append('-no-dbus')
        
        # OpenSSL 配置
        if tag_options.get('openssl-runtime'):
            result.append('-openssl-runtime')
            result.append('OPENSSL_INCDIR={}'.format(os.path.join(self.openssl_path, 'include')))
        
        # rpath 配置
        if tag_options.get('-disable-rpath'):
            result.append('-disable-rpath')
        
        # nomake 选项
        for nomake in tag_options.get('-nomake', []):
            result += ['-nomake', nomake]
        
        # skip 选项
        skips = tag_options.get('-skip', [])
        for skip in skips:
            result += ['-skip', skip]
        
        # 构建目录和类型
        result += ['-prefix', self.build_prefix()]
        result += ['-{}'.format(self.build_type())]
        
        # Qt5 特定选项
        result += ['-device-option', 'OHOS_ARCH={}'.format(self.build_ohos_abi())]
        result += ['-make-tool', '{} -j{}'.format(self.make_tools, self.build_jobs())]
        
        # 特性选项
        features = self.get_config_value('features')
        for feature in features:
            result += ['-feature-{}'.format(feature)]
        
        # verbose 选项
        if self.get_config_value('verbose'):
            result += ['-verbose']
        
        return result
    
    def build_host_configure_options(self):
        """Qt6 主机编译的配置选项（从 qt6-host-config[tag] 读取）"""
        # 从 qt6-host-config 中获取当前版本的配置
        qt6_host_config = self.config.get('qt6-host-config', {})
        tag_options = qt6_host_config.get(self.tag(), {})
        
        if not tag_options:
            raise ValueError(f'配置文件中未找到Qt6主机版本 {self.tag()} 的配置')
        
        result = []
        
        # 基本选项（从父级获取）
        if qt6_host_config.get('license') in ['opensource', 'commercial']:
            result.append('-{}'.format(qt6_host_config['license']))
        if qt6_host_config.get('confirm-license'):
            result.append('-confirm-license')
        
        # 主机平台
        host_platform = 'win32-g++'
        if platform.system() == 'Linux':
            host_platform = 'linux-g++'
        elif platform.system() == 'Darwin':
            host_platform = 'macx-clang'
        result += ['-platform', host_platform]
        
        # 构建类型和安装路径
        result += ['-{}'.format(self.build_type())]
        result += ['-prefix', self.build_host_prefix()]
        
        # Qt6 主机编译：开发者模式（如果配置中指定）
        if tag_options.get('-developer-build'):
            result.append('-developer-build')
        
        # nomake选项
        for nomake in tag_options.get('-nomake', []):
            result += ['-nomake', nomake]
        
        # skip选项
        skips = tag_options.get('-skip', [])
        for skip in skips:
            result += ['-skip', skip]
        
        # verbose选项
        if self.get_config_value('verbose'):
            result += ['-verbose']
        
        return result
    
    def build_cross_configure_options(self):
        """Qt6交叉编译的配置选项（用于OHOS目标平台）"""
        # 从 qt6-cross-config 中获取当前版本的配置
        qt6_cross_config = self.config.get('qt6-cross-config', {})
        tag_options = qt6_cross_config.get(self.tag(), {})
        
        if not tag_options:
            raise ValueError(f'配置文件中未找到Qt6交叉编译版本 {self.tag()} 的配置')
        
        result = []
        
        # 基本选项（从父级获取）
        if qt6_cross_config.get('license') in ['opensource', 'commercial']:
            result.append('-{}'.format(qt6_cross_config['license']))
        if qt6_cross_config.get('confirm-license'):
            result.append('-confirm-license')
        
        # Qt6交叉编译不需要-platform参数，只需要-xplatform和OHOS SDK相关配置
        result += ['-xplatform', tag_options.get('-xplatform', 'ohos-clang')]
        result += ['-openharmony-sdk', self.ohos_sdk_path]
        result += ['-openharmony-abis', self.build_ohos_abi()]
        
        # OpenGL设置
        if '-opengl' in tag_options:
            result += ['-opengl', tag_options['-opengl']]
        if tag_options.get('-opengles3'):
            result.append('-opengles3')
        
        # DBus设置
        if tag_options.get('-no-dbus'):
            result.append('-no-dbus')
        
        # OpenSSL设置
        if tag_options.get('openssl-runtime'):
            result.append('-openssl-runtime')
        
        # rpath设置
        if tag_options.get('-disable-rpath'):
            result.append('-disable-rpath')
        
        # nomake选项
        for nomake in tag_options.get('-nomake', []):
            result += ['-nomake', nomake]
        
        # skip选项
        skips = tag_options.get('-skip', [])
        for skip in skips:
            result += ['-skip', skip]
        
        # 构建类型和安装路径
        result += ['-{}'.format(self.build_type())]
        result += ['-prefix', self.build_prefix()]
        
        # 指定主机工具路径
        result += ['-qt-host-path', self.build_host_prefix()]
        
        # 特性选项
        features = self.get_config_value('features')
        for feature in features:
            result += ['-feature-{}'.format(feature)]
        
        # verbose选项
        if self.get_config_value('verbose'):
            result += ['-verbose']
        
        return result
    
    def build_host_cmake_options(self):
        """Qt6主机编译的CMake选项（从 qt6-host-config[tag]['cmake-options'] 读取）"""
        # 从 qt6-host-config 中获取当前版本的 CMake 配置
        qt6_host_config = self.config.get('qt6-host-config', {})
        tag_options = qt6_host_config.get(self.tag(), {})
        cmake_options = tag_options.get('cmake-options', {})
        
        result = []
        
        # 将 cmake-options 字典转换为 CMake 命令行参数
        for key, value in cmake_options.items():
            if isinstance(value, bool):
                # 布尔值转换为 ON/OFF
                result.append(f'-D{key}={"ON" if value else "OFF"}')
            elif isinstance(value, (int, float, str)):
                # 其他类型直接转换为字符串
                result.append(f'-D{key}={value}')
        
        return result
    
    def build_cross_cmake_options(self):
        """Qt6交叉编译的CMake选项（从 qt6-cross-config[tag]['cmake-options'] 读取）"""
        # 从 qt6-cross-config 中获取当前版本的 CMake 配置
        qt6_cross_config = self.config.get('qt6-cross-config', {})
        tag_options = qt6_cross_config.get(self.tag(), {})
        cmake_options = tag_options.get('cmake-options', {})
        
        result = []
        
        # 将 cmake-options 字典转换为 CMake 命令行参数
        for key, value in cmake_options.items():
            if isinstance(value, bool):
                # 布尔值转换为 ON/OFF
                result.append(f'-D{key}={"ON" if value else "OFF"}')
            elif isinstance(value, (int, float, str)):
                # 其他类型直接转换为字符串
                result.append(f'-D{key}={value}')
        
        return result
