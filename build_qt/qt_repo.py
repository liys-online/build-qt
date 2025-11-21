"""qt_repo.py

基于 GitPython 的 Qt 源码拉取与管理类

功能：
- 克隆（指定分支或 tag）
- 支持克隆深度（depth）
- 子模块初始化与更新（可递归、可浅克隆）

设计要点：
- 对于大型仓库（如 Qt），默认尽量使用浅克隆并在需要时按需更新子模块
"""
from typing import Optional, List
import os
import shutil
import subprocess
from build_qt.config import Config
from build_qt.utils import download_component, extract_archive

class QtRepoError(Exception):
    pass


class QtRepo:
    """Qt仓库管理类。

    参数：
    - repo_path: 本地目标目录
    - remote_name: 远端名，默认 origin
    """
    def __init__(self, repo_path: str, config: Config, remote_name: str = 'origin'):
        self.repo_path = os.path.abspath(repo_path)
        self.patch_repo_path = self.repo_path + '_patch'
        self.remote_name = remote_name
        self.config = config
        self.git_exe = shutil.which('git')
        if not self.git_exe:
            print('系统中未找到 git 可执行文件')
            temp_dir = os.path.join(self.config.get_working_dir(), '.temp')
            depends_git = config.get_depends().get('git')
            git_url = depends_git.get('gh_url') if self.config.use_gh else depends_git.get('gc_url')
            git_checksum = ('sha256', depends_git.get('sha256'))
            download_path = os.path.join(temp_dir, 'Git-2.51.2-windows-64-bit.7z')
            print('正在下载并安装 Git...')
            zip_path = download_component(git_url, download_path, git_checksum)
            git_extracted_path = os.path.join(self.config.get_working_dir(), 'git')
            extract_archive(zip_path, git_extracted_path)
            if os.path.isdir(git_extracted_path):
                self.git_exe = os.path.join(git_extracted_path, 'bin', 'git')
            else:
                raise QtRepoError('Git 解压失败: {}'.format(git_extracted_path))

    # ---------- 克隆相关 ----------
    def clone(self) -> None:
        """克隆仓库。

        depth: 0 表示完整克隆；>0 表示使用 --depth
        branch: 若指定，传递给 git clone 的 --branch
        """
        url = self.config.qt_repo()
        depth = self.config.clone_depth()
        branch = self.config.tag()
        if os.path.exists(self.repo_path) and os.listdir(self.repo_path):
            print('目录已存在: {}, 跳过克隆'.format(self.repo_path))
            return

        cmd = [self.git_exe, 'clone', '--recurse-submodules', '--single-branch', '--shallow-submodules']
        if depth and depth > 0:
            cmd += ['--depth', str(depth)]
        if branch:
            cmd += ['--branch', branch]
        cmd += [url, self.repo_path]

        print(' '.join(cmd))
        if subprocess.run(cmd, check=True).returncode == 0:
            print('Clone succeeded. Remote URL: {}'.format(self.config.qt_repo()))
        else:
            raise QtRepoError('git clone 失败: {}'.format(url))
        print('Local branches: {}'.format(self.list_branches(local=True)))

    def clone_patch_repo(self, depth: int = 0) -> None:
        """克隆补丁仓库，位于主仓库同级目录的 repo_path + '_patch' 目录下。"""
        url = self.config.qt_ohos_patch_repo()
        branch = self.config.ohqt_tag()
        patch_path = self.repo_path + '_patch'
        if os.path.exists(patch_path) and os.listdir(patch_path):
            print('目录已存在: {}, 跳过克隆'.format(patch_path))
            return

        cmd = [self.git_exe, 'clone', '--single-branch']
        if depth and depth > 0:
            cmd += ['--depth', str(depth)]
        if branch:
            cmd += ['--branch', branch]
        cmd += [url, patch_path]

        print(' '.join(cmd))
        if subprocess.run(cmd, check=True).returncode == 0:
            print('Clone Patch succeeded. Remote URL: {}'.format(self.config.qt_ohos_patch_repo()))
        else:
            raise QtRepoError('git clone 补丁仓库失败: {}'.format(url))

    def apply_patches(self) -> None:
        """应用补丁仓库中的补丁文件到主仓库。

        patch_dir: 补丁文件所在目录，默认使用补丁仓库根目录
        """

        if not os.path.isdir(os.path.join(self.repo_path, '.git')):
            raise QtRepoError('主仓库未初始化')

        if not os.path.isdir(os.path.join(self.patch_repo_path, '.git')):
            raise QtRepoError('补丁仓库未初始化')

        self.reset_hard()
        tag_dir = self.config.tag()
        if tag_dir:
            tag_dir = tag_dir.replace('-lts-lgpl', '')
        else:
            tag_dir = 'v5.15.12'  # 默认使用 v5.15.12 目录
        patch_dir = os.path.join(self.patch_repo_path, 'patch', tag_dir)
        if not os.path.isdir(patch_dir):
            raise QtRepoError('补丁目录不存在: {}'.format(patch_dir))

        patch_files = [f for f in os.listdir(patch_dir) if f.endswith('.patch')]
        if not patch_files:
            raise QtRepoError('补丁目录中没有 .patch 文件: {}'.format(patch_dir))

        for patch_file in sorted(patch_files):
            patch_path = os.path.join(patch_dir, patch_file)
            if patch_file == 'root.patch':
                cmd = [self.git_exe, '-C', self.repo_path, 'apply', patch_path]
                print(' '.join(cmd))
                if subprocess.run(cmd, stderr=subprocess.DEVNULL, check=True).returncode == 0:
                    print('应用补丁 {} 成功'.format(patch_file))
                else:
                    raise QtRepoError('应用补丁 {} 失败'.format(patch_file))
            else:
                module_repo_path = self.repo_path + '/' + patch_file.split('.')[0]
                cmd = [self.git_exe, '-C', module_repo_path, 'apply', patch_path]
                print(' '.join(cmd))
                if subprocess.run(cmd, stderr=subprocess.DEVNULL, check=True).returncode == 0:
                    print('应用补丁 {} 成功'.format(patch_file))
                else:
                    raise QtRepoError('应用补丁 {} 失败'.format(patch_file))
        # 拷贝patch目录下的qtohextras到qt源码根目录
        qtohextras_dir = patch_dir = os.path.join(self.patch_repo_path, 'patch', 'qtohextras')
        if os.path.isdir(qtohextras_dir):
            dest_dir = os.path.join(self.repo_path, 'qtohextras')
            if os.path.exists(dest_dir):
                shutil.rmtree(dest_dir)
            shutil.copytree(qtohextras_dir, dest_dir)
            qtohextras_git = os.path.join(dest_dir, '.git')
            with open(qtohextras_git, "w") as f:
                f.write('gitdir: ../.git/modules/qtohextras')
            print('拷贝 qtohextras 目录成功')
        print('所有补丁应用完成')

    # ---------- 分支管理 ----------
    def list_branches(self, local: bool = True, remote: bool = False) -> List[str]:
        if not os.path.isdir(os.path.join(self.repo_path, '.git')):
            raise QtRepoError('仓库未初始化')
        out = []
        if local:
            cmd = [self.git_exe, '-C', self.repo_path, 'branch']
            try:
                result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                branches = result.stdout.strip().split('\n')
                for branch in branches:
                    out.append(branch.strip().lstrip('* ').strip())
            except subprocess.CalledProcessError as e:
                raise QtRepoError('列出本地分支 失败: {}'.format(e))
        if remote:
            cmd = [self.git_exe, '-C', self.repo_path, 'branch', '-r']
            try:
                result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                branches = result.stdout.strip().split('\n')
                for branch in branches:
                    out.append(branch.strip())
            except subprocess.CalledProcessError as e:
                raise QtRepoError('列出远端分支 失败: {}'.format(e))
        return out

    # ---------- 重置 ----------
    def reset_hard(self):
        try:
            # 1. 重置主仓库
            cmd = [self.git_exe, '-C', self.repo_path, 'reset', '--hard']

            try:
                print(' '.join(cmd))
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                raise QtRepoError('重置主仓库 失败: {}'.format(e))
            
            cmd = [self.git_exe, '-C', self.repo_path, 'submodule', 'foreach', '--recursive', 'git', 'reset', '--hard']
            try:
                print(' '.join(cmd))
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                raise QtRepoError('重置子仓库 失败: {}'.format(e))
            self.clean()
        except Exception as e:
            raise QtRepoError('重置失败: {}'.format(e))
        
    def clean(self):
        try:
            # 1. 清理主仓库
            cmd = [self.git_exe, '-C', self.repo_path, 'clean' , '-fdx']
            try:
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                raise QtRepoError('清理主仓库 失败: {}'.format(e))
            
            cmd = [self.git_exe, '-C', self.repo_path, 'submodule', 'foreach', '--recursive', 'git', 'clean' , '-fdx']
            try:
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                raise QtRepoError('清理子仓库 失败: {}'.format(e))
        except Exception as e:
            raise QtRepoError('清理失败: {}'.format(e))


if __name__ == '__main__':
    print('This module provides QtRepo class using GitPython')
