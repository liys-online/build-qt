"""qt6_build.py

Qt6构建管理类，专门处理Qt6的编译流程

特点：
- 支持主机编译（host build）和交叉编译（cross compile）
- 自动配置CMake环境
- 自动复制必要的DLL依赖
"""
import platform
import os
import subprocess
from .utils import create_archive
from .config import Config
import shutil
import datetime


class Qt6Build:
    """Qt6构建管理类，处理Qt6的两阶段编译流程
    
    方案1：使用独立的源码树
    - host_source_dir: 主机编译专用源码（qt6_host）
    - cross_source_dir: 交叉编译专用源码（qt6）
    - 完全隔离两个构建过程，避免CMake目标冲突
    """
    
    def __init__(self, source_dir: str, config: Config):
        # 交叉编译使用主源码目录
        self.cross_source_dir = source_dir
        # 保持向后兼容
        self.source_dir = source_dir
        
        # 主机编译使用独立的源码目录（方案1：独立源码树）
        work_dir = config.get_working_dir()
        self.host_source_dir = os.path.join(work_dir, 'qt6_host')
        
        self.config = config
        self.system = platform.system()
        self.supported_systems = ['Windows', 'Linux', 'Darwin']
        
        if self.system not in self.supported_systems:
            raise EnvironmentError('Unsupported system: {}'.format(self.system))
        
        # Qt6使用cmake作为构建工具，使用OHOS SDK中的cmake
        ohos_sdk_path = config.get_path('ohos_sdk')
        cmake_bin_path = os.path.join(ohos_sdk_path, 'native', 'build-tools', 'cmake', 'bin')
        self.cmake_cmd = os.path.join(cmake_bin_path, 'cmake.exe' if self.system == 'Windows' else 'cmake')
        
        # 检查cmake是否存在
        if not os.path.isfile(self.cmake_cmd):
            # 如果cmake不存在，尝试使用系统的cmake
            system_cmake = shutil.which('cmake')
            if system_cmake:
                self.cmake_cmd = system_cmake
                print('使用系统的cmake: {}'.format(system_cmake))
            else:
                raise EnvironmentError('CMake未找到，请确保OHOS SDK中包含CMake或系统中安装了CMake')
        
        # Qt6需要两个构建目录：主机编译和交叉编译
        # 将构建目录放在work目录下，避免补丁应用时被清理
        self.host_build_dir = os.path.join(work_dir, 'qt6_build', 'host')
        self.cross_build_dir = os.path.join(work_dir, 'qt6_build', config.build_type())
        
        # 创建构建目录
        if not os.path.exists(self.host_build_dir):
            os.makedirs(self.host_build_dir)
            print('创建主机构建目录: {}'.format(self.host_build_dir))
        if not os.path.exists(self.cross_build_dir):
            os.makedirs(self.cross_build_dir)
            print('创建交叉编译目录: {}'.format(self.cross_build_dir))
    
    def setup_environment(self):
        """设置Qt6编译所需的环境变量"""
        # 1. 设置CMake路径（来自OHOS SDK）
        ohos_sdk_path = self.config.get_path('ohos_sdk')
        cmake_bin_path = os.path.join(ohos_sdk_path, 'native', 'build-tools', 'cmake', 'bin')
        
        if os.path.isdir(cmake_bin_path):
            os.environ['PATH'] = cmake_bin_path + os.pathsep + os.environ.get('PATH', '')
            print('已添加OHOS SDK CMake到环境变量: {}'.format(cmake_bin_path))
        else:
            print('警告: 未找到OHOS SDK CMake路径: {}'.format(cmake_bin_path))
        
        # 2. 设置MinGW路径
        mingw_path = self.config.get_build_tool_path('mingw')
        if mingw_path and os.path.isdir(mingw_path):
            os.environ['PATH'] = mingw_path + os.pathsep + os.environ.get('PATH', '')
            print('已添加MinGW到环境变量: {}'.format(mingw_path))
    
    def copy_mingw_dlls(self, target_bin_dir: str):
        """复制MinGW的DLL依赖到指定目录
        
        Args:
            target_bin_dir: 目标bin目录路径
        """
        dll_deps = ['libstdc++-6.dll', 'libgcc_s_seh-1.dll', 'libwinpthread-1.dll']
        mingw_bin = self.config.get_build_tool_path('mingw')
        
        if not os.path.exists(target_bin_dir):
            os.makedirs(target_bin_dir)
        
        for dll_dep in dll_deps:
            src_dll = os.path.join(mingw_bin, dll_dep)
            dst_dll = os.path.join(target_bin_dir, dll_dep)
            if os.path.exists(src_dll):
                shutil.copy(src_dll, dst_dll)
                print('已复制依赖 DLL: {} -> {}'.format(dll_dep, target_bin_dir))
            else:
                print('警告: 未找到依赖 DLL: {}'.format(src_dll))
    
    def configure_host(self):
        """配置Qt6主机编译（不进行交叉编译）"""
        print('\n========== 开始Qt6主机编译配置 ==========')
        self.setup_environment()
        
        configure_script = os.path.join(self.source_dir, 'configure.bat' if self.system == 'Windows' else 'configure')
        # 添加-redo参数以清理CMakeCache.txt，确保能够重新配置
        cmd = [configure_script] + self.config.build_host_configure_options()
        
        print('主机编译配置命令：', ' '.join(cmd))
        result = subprocess.run(cmd, cwd=self.host_build_dir, check=True)
        
        if result.returncode == 0:
            print('主机编译配置成功')
            # 复制MinGW DLL到主机构建的qmake目录
            qmake_dir = os.path.join(self.config.build_host_prefix(), 'bin')
            self.copy_mingw_dlls(qmake_dir)
        else:
            raise RuntimeError('主机编译配置失败')
    
    def build_host(self, jobs: int = 4):
        """执行Qt6主机编译"""
        print('\n========== 开始Qt6主机编译 ==========')
        self.setup_environment()  # 确保环境变量正确设置
        
        build_cmd = [self.cmake_cmd, '--build', '.', '--parallel', str(jobs)]
        print('主机编译命令：', ' '.join(build_cmd))
        print('CMake路径: {}'.format(self.cmake_cmd))
        print('构建目录: {}'.format(self.host_build_dir))
        result = subprocess.run(build_cmd, cwd=self.host_build_dir, check=True)
        
        if result.returncode == 0:
            print('主机编译成功')
        else:
            raise RuntimeError('主机编译失败')
    
    def install_host(self):
        """安装Qt6主机编译结果"""
        print('\n========== 开始Qt6主机编译安装 ==========')
        install_cmd = [self.cmake_cmd, '--install', '.']
        print('主机编译安装命令:', ' '.join(install_cmd))
        result = subprocess.run(install_cmd, cwd=self.host_build_dir, check=True)
        
        if result.returncode == 0:
            print('主机编译安装成功')
            print('主机编译安装目录: {}'.format(self.config.build_host_prefix()))
        else:
            raise RuntimeError('主机编译安装失败')
    
    def configure_cross(self):
        """配置Qt6交叉编译（用于OHOS目标平台）"""
        print('\n========== 开始Qt6交叉编译配置 ==========')
        self.setup_environment()
        
        configure_script = os.path.join(self.source_dir, 'configure.bat' if self.system == 'Windows' else 'configure')
        # 添加-redo参数以清理CMakeCache.txt，确保能够重新配置
        cmd = [configure_script] + self.config.build_cross_configure_options()
        
        # Qt6交叉编译通过CMake参数指定OpenSSL路径和强制构建工具
        cmd.append('--')
        if self.config.openssl_runtime():
            openssl_root = self.config.get_path('openssl')
            cmd.append('-DOPENSSL_ROOT_DIR={}'.format(openssl_root))
        # 交叉编译需要强制构建工具，因为交叉编译包需要提供给第三方使用
        cmd.append('-DQT_FORCE_BUILD_TOOLS=1')
        # Windows上使用Ninja生成器时，需要设置CMAKE_BUILD_WITH_INSTALL_RPATH避免RPATH重链接问题
        cmd.append('-DCMAKE_BUILD_WITH_INSTALL_RPATH=ON')
        
        print('交叉编译配置命令：', ' '.join(cmd))
        result = subprocess.run(cmd, cwd=self.cross_build_dir, check=True)
        
        if result.returncode == 0:
            print('交叉编译配置成功')
            # 复制MinGW DLL到交叉编译的qmake目录
            qmake_dir = os.path.join(self.config.build_prefix(), 'bin')
            self.copy_mingw_dlls(qmake_dir)
        else:
            raise RuntimeError('交叉编译配置失败')
    
    def build_cross(self, jobs: int = 4):
        """执行Qt6交叉编译"""
        print('\n========== 开始Qt6交叉编译 ==========')
        self.setup_environment()  # 确保环境变量正确设置
        
        build_cmd = [self.cmake_cmd, '--build', '.', '--parallel', str(jobs)]
        print('交叉编译命令：', ' '.join(build_cmd))
        print('CMake路径: {}'.format(self.cmake_cmd))
        print('构建目录: {}'.format(self.cross_build_dir))
        result = subprocess.run(build_cmd, cwd=self.cross_build_dir, check=True)
        
        if result.returncode == 0:
            print('交叉编译成功')
        else:
            raise RuntimeError('交叉编译失败')
    
    def install_cross(self):
        """安装Qt6交叉编译结果"""
        print('\n========== 开始Qt6交叉编译安装 ==========')
        install_cmd = [self.cmake_cmd, '--install', '.']
        print('交叉编译安装命令:', ' '.join(install_cmd))
        result = subprocess.run(install_cmd, cwd=self.cross_build_dir, check=True)
        
        if result.returncode == 0:
            print('交叉编译安装成功')
            print('交叉编译安装目录: {}'.format(self.config.build_prefix()))
            
            # 复制OpenSSL依赖（如果需要）
            if self.config.openssl_runtime():
                self._copy_openssl_libs()
        else:
            raise RuntimeError('交叉编译安装失败')
    
    def _copy_openssl_libs(self):
        """复制OpenSSL库文件"""
        openssl_lib = os.path.join(self.config.get_path('openssl'), 'lib')
        target_lib = os.path.join(self.config.build_prefix(), 'lib')
        
        for so in ['libcrypto.so', 'libcrypto.so.1.1', 'libssl.so', 'libssl.so.1.1']:
            src_lib = os.path.join(openssl_lib, so)
            if os.path.exists(src_lib):
                shutil.copy(src_lib, target_lib)
                print('已复制 OpenSSL 依赖: {}'.format(so))
            else:
                print('未找到 OpenSSL 依赖: {}'.format(so))
    
    def _clean_source_generated_files(self):
        """使用git clean清理源码树中所有生成的文件
        
        这会删除所有未跟踪的文件，包括主机编译生成的CMake文件和中间产物
        """
        print('使用git clean清理源码树生成文件...')
        
        from .qt_repo import QtRepo
        qt_repo = QtRepo(self.source_dir, self.config)
        
        # 使用git clean -fdx清理所有未跟踪的文件和目录
        # -f: force
        # -d: 删除未跟踪的目录
        # -x: 删除被.gitignore忽略的文件
        cmd = [qt_repo.git_exe, 'clean', '-fdx']
        
        print('执行命令: {}'.format(' '.join(cmd)))
        print('工作目录: {}'.format(self.source_dir))
        
        try:
            result = subprocess.run(cmd, cwd=self.source_dir, 
                                  capture_output=True, text=True, check=True)
            if result.stdout:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 10:
                    print('  清理了 {} 个文件/目录'.format(len(lines)))
                    for line in lines[:5]:
                        print('  {}'.format(line))
                    print('  ...')
                else:
                    for line in lines:
                        print('  {}'.format(line))
            print('源码树生成文件清理完成')
        except subprocess.CalledProcessError as e:
            print('警告: git clean失败: {}'.format(e))
            if e.stderr:
                print('错误信息: {}'.format(e.stderr))
    
    def _clean_cross_build_dir(self):
        """清理交叉编译构建目录，避免主机编译和交叉编译的插件定义冲突
        
        这是最安全的方法：删除整个交叉编译构建目录并重新创建
        """
        if os.path.exists(self.cross_build_dir):
            print('删除交叉编译构建目录: {}'.format(self.cross_build_dir))
            try:
                shutil.rmtree(self.cross_build_dir, ignore_errors=True)
                print('交叉编译构建目录已删除')
            except Exception as e:
                print('警告: 删除构建目录时出错: {}'.format(e))
        
        # 重新创建干净的构建目录
        os.makedirs(self.cross_build_dir)
        print('已创建新的交叉编译构建目录: {}'.format(self.cross_build_dir))
    
    def configure(self):
        """配置阶段：主机编译配置"""
        self.configure_host()
    
    def build(self, jobs: int = 4):
        """构建阶段：先主机编译并安装，应用补丁，再交叉编译"""
        # self.build_host(jobs)
        # self.install_host()  # 主机编译后立即安装，确保-qt-host-path可用
        
        # Qt6主机编译后，先清理源码树，再应用补丁
        # 清理源码树中主机编译生成的所有文件
        print('\n========== 清理源码树生成文件 ==========')
        self._clean_source_generated_files()
        
        # 清理后应用patch补丁
        print('\n========== 应用Qt6补丁 ==========')
        from .qt_repo import QtRepo
        qt_repo = QtRepo(self.source_dir, self.config)
        try:
            qt_repo.apply_patches()
            print('补丁应用成功')
        except Exception as e:
            print('警告: 补丁应用失败或已应用: {}'.format(e))
        
        # 清理交叉编译构建目录，确保从干净状态开始
        print('\n========== 清理交叉编译构建目录 ==========')
        self._clean_cross_build_dir()
        
        self.configure_cross()
        self.build_cross(jobs)
    
    def install(self):
        """安装阶段：安装交叉编译结果（主机编译安装已在build阶段完成）"""
        self.install_cross()
    
    def clean(self):
        """清理构建目录"""
        for build_dir in [self.host_build_dir, self.cross_build_dir]:
            if os.path.exists(build_dir):
                print('正在删除构建目录: {}'.format(build_dir))
                shutil.rmtree(build_dir, ignore_errors=True)
                print('构建目录已删除')
    
    def pack(self):
        """打包编译结果"""
        prefix = self.config.build_prefix()
        if not prefix:
            raise ValueError('安装路径未设置，无法打包')
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M")
        suffix = 'zip' if self.system == 'Windows' else 'tar.gz'
        
        package_name = 'Qt{}_OHOS{}_{}_{}_{}.{}'.format(
            self.config.qt_version(),
            self.config.ohos_version(),
            self.config.build_ohos_abi(),
            self.system.lower(),
            timestamp,
            suffix
        )
        
        package_name = os.path.join(self.config.get_output_path(), package_name)
        create_archive(prefix, package_name, _format=suffix)
    
    def print_build_info(self):
        """打印构建信息"""
        print('Qt6构建信息:')
        print('  系统: {}'.format(self.system))
        print('  源码目录: {}'.format(self.source_dir))
        print('  主机构建目录: {}'.format(self.host_build_dir))
        print('  交叉编译目录: {}'.format(self.cross_build_dir))
        print('  主机安装目录: {}'.format(self.config.build_host_prefix()))
        print('  交叉编译安装目录: {}'.format(self.config.build_prefix()))
