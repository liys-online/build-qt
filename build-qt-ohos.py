import os
import sys
import io
import argparse
from build_qt.qt_repo import QtRepo, QtRepoError
from build_qt.qt_build import QtBuild
from build_qt.config import Config

def init_parser():
    parser = argparse.ArgumentParser(description='Build Qt for OHOS')
    parser.add_argument('--init', action='store_true', help='初始化Qt仓库,并应用补丁')
    parser.add_argument('--env_check', action='store_true', help='检查开发环境')
    parser.add_argument('--reset_repo', action='store_true', help='重置Qt仓库,并重新应用补丁')
    build_stages = ['configure', 'build', 'install', 'clean', 'all', "print_build_info"]
    parser.add_argument('--exe_stage', type=str, choices=build_stages, help='执行指定阶段')
    parser.add_argument("--with_pack", action="store_true", help="编译后是否打包编译结果")
    parser.add_argument('--use_github', action='store_true', help='使用GitHub地址')
    _args = parser.parse_args()
    if not any(vars(_args).values()):
        parser.print_help()
        exit(0)
    return _args

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stdout.reconfigure(line_buffering=True)
    args = init_parser()
    config = Config(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'configure.json'), args.use_github)
    qt_dir = os.path.join(config.get_working_dir(), 'qt5')

    repo = QtRepo(qt_dir, config)
    if args.init:
        try:
            # Qt源码克隆
            repo.clone()

            # Qt OHOS补丁仓库克隆
            repo.clone_patch_repo()

            # 应用补丁
            repo.apply_patches()
        except QtRepoError as e:
            print('QtRepoError:', e)
            exit(1)
        except Exception as e:
            print('Error:', e)
            exit(1)
        exit()
    if args.reset_repo:
        try:
            # 重新应用补丁
            repo.apply_patches()
        except QtRepoError as e:
            print('QtRepoError:', e)
            exit(1)
        except Exception as e:
            print('Error:', e)
            exit(1)
        exit()
    if args.exe_stage is not None or args.env_check:
        # 开发环境检查
        config.dev_env_check()
        if args.env_check:
            exit()
        # Qt编译
        qtBuild = QtBuild(qt_dir, config)
        # 配置
        if args.exe_stage == 'clean':
            qtBuild.clean()
            exit()
        if args.exe_stage == 'configure' or args.exe_stage == 'all':
            try:
                qtBuild.configure()
            except Exception as e:
                print('Error during configuration:', e)
                exit(1)
        # 构建
        if args.exe_stage == 'build' or args.exe_stage == 'all':
            try:
                qtBuild.build(config.build_jobs())
            except Exception as e:
                print('Error during build:', e)
                exit(1)
        # 安装
        if args.exe_stage == 'install' or args.exe_stage == 'all':
            try:
                qtBuild.install()
            except Exception as e:
                print('Error during install:', e)
                exit(1)
        # 打包
        if args.with_pack:
            try:
                qtBuild.pack()
            except Exception as e:
                print('Error during pack:', e)
                exit(1)

        if args.exe_stage == 'print_build_info':
            qtBuild.print_build_info()
    exit()

