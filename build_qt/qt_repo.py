"""qt_repo.py

基于 GitPython 的 Qt 源码拉取与管理类

功能：
- 克隆（指定分支或 tag）
- 支持克隆深度（depth）
- 子模块初始化与更新（可递归、可浅克隆）
- 切换/创建/删除分支
- fetch/pull/reset_hard
- 设置/查询远端 URL

设计要点：
- 使用 GitPython (git CLI 作为后端)，行为与系统 git 一致
- 对于大型仓库（如 Qt），默认尽量使用浅克隆并在需要时按需更新子模块
"""
from typing import Optional, List
import os
import shutil
import subprocess
from git import Repo, GitCommandError
from build_qt.config import Config
from build_qt.utils import download_component, extract_archive

class QtRepoError(Exception):
    pass


class QtRepo:
    """用 GitPython 封装的仓库管理类。

    参数：
    - repo_path: 本地目标目录
    - remote_name: 远端名，默认 origin
    """
    def __init__(self, repo_path: str, config: Config, remote_name: str = 'origin'):
        self.repo_path = os.path.abspath(repo_path)
        self.remote_name = remote_name
        self.config = config
        self.repo = None
        self.patch_repo = None
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

        if os.path.isdir(os.path.join(self.repo_path, '.git')):
            try:
                self.repo = Repo(self.repo_path)
            except Exception as e:
                raise QtRepoError('打开仓库失败: {}'.format(e))

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
            self.repo = Repo(self.repo_path)
            return

        cmd = [self.git_exe, 'clone', '--recurse-submodules', '--single-branch', '--shallow-submodules']
        if depth and depth > 0:
            cmd += ['--depth', str(depth)]
        if branch:
            cmd += ['--branch', branch]
        cmd += [url, self.repo_path]

        try:
            print('Cloning {} to {} with depth={}'.format(url, self.repo_path, depth))
            subprocess.run(cmd, check=True)
            self.repo = Repo(self.repo_path)
            print('Clone succeeded. Remote URL: {}'.format(self.repo.remotes[self.remote_name].url))
        except subprocess.CalledProcessError as e:
            raise QtRepoError('git clone 失败: {}'.format(e))
        print('Local branches: {}'.format(self.list_branches(local=True)))

    def clone_patch_repo(self, depth: int = 0) -> None:
        """克隆补丁仓库，位于主仓库同级目录的 repo_path + '_patch' 目录下。"""
        url = self.config.qt_ohos_patch_repo()
        patch_path = self.repo_path + '_patch'
        if os.path.exists(patch_path) and os.listdir(patch_path):
            print('目录已存在: {}, 跳过克隆'.format(patch_path))
            self.patch_repo = Repo(patch_path)
            return

        cmd = [self.git_exe, 'clone', '--single-branch']
        if depth and depth > 0:
            cmd += ['--depth', str(depth)]
        cmd += [url, patch_path]

        try:
            print('Cloning patch repo {} to {} with depth={}'.format(url, patch_path, depth))
            subprocess.run(cmd, check=True)
            self.patch_repo = Repo(patch_path)
            print('Patch repo clone succeeded. Remote URL: {}'.format(self.patch_repo.remotes[self.remote_name].url))
        except subprocess.CalledProcessError as e:
            raise QtRepoError('git clone 补丁仓库失败: {}'.format(e))
    
    def apply_patches(self, tag_dir: Optional[str] = None) -> None:
        """应用补丁仓库中的补丁文件到主仓库。

        patch_dir: 补丁文件所在目录，默认使用补丁仓库根目录
        """

        if not self.repo:
            if os.path.isdir(os.path.join(self.repo_path, '.git')):
                self.repo = Repo(self.repo_path)
            else:
                raise QtRepoError('主仓库未初始化')

        if not self.patch_repo:
            if os.path.isdir(os.path.join(self.repo_path + '_patch', '.git')):
                self.patch_repo = Repo(self.repo_path + '_patch')
            else:
                raise QtRepoError('补丁仓库未初始化')

        self.reset_hard()
        if tag_dir:
            tag_dir = tag_dir.replace('-lts-lgpl', '')
        else:
            tag_dir = 'v5.15.12'  # 默认使用 v5.15.12 目录
        patch_dir = os.path.join(self.patch_repo.working_tree_dir, 'patch', tag_dir)
        if not os.path.isdir(patch_dir):
            raise QtRepoError('补丁目录不存在: {}'.format(patch_dir))

        patch_files = [f for f in os.listdir(patch_dir) if f.endswith('.patch')]
        if not patch_files:
            raise QtRepoError('补丁目录中没有 .patch 文件: {}'.format(patch_dir))

        for patch_file in sorted(patch_files):
            patch_path = os.path.join(patch_dir, patch_file)
            if patch_file == 'root.patch':
                self.repo.git.apply(patch_path)
            else:
                try:
                    module_repo = Repo(self.repo_path + '/' + patch_file.split('.')[0])
                    module_repo.git.apply(patch_path, '--whitespace=nowarn')
                    print('应用补丁 {} 成功'.format(patch_file))
                except GitCommandError as e:
                    raise QtRepoError('应用补丁 {} 失败: {}'.format(patch_file, e))
        # 拷贝patch目录下的qtohextras到qt源码根目录
        qtohextras_dir = os.path.join(patch_dir, 'qtohextras')
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
    # ---------- 远端/fetch/pull ----------
    def fetch(self, remote_name: Optional[str] = None) -> None:
        if not self.repo:
            raise QtRepoError('仓库未初始化')
        try:
            r = self.repo.remotes[remote_name or self.remote_name]
            r.fetch()
        except Exception as e:
            raise QtRepoError('fetch 失败: {}'.format(e))

    # ---------- 分支管理 ----------
    def list_branches(self, local: bool = True, remote: bool = False) -> List[str]:
        if not self.repo:
            raise QtRepoError('仓库未初始化')
        out = []
        if local:
            out += [h.name for h in self.repo.branches]
        if remote:
            out += [r.name for r in self.repo.remotes]
        return out

    def checkout(self, name: str) -> None:
        if not self.repo:
            raise QtRepoError('仓库未初始化')
        try:
            self.repo.git.checkout(name)
        except Exception as e:
            raise QtRepoError('checkout 失败: {}'.format(e))

    # ---------- 重置 ----------
    def reset_hard(self):
        try:
            # 1. 重置主仓库
            cmd = [self.git_exe, '-C', self.repo_path, 'reset', '--hard']

            try:
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                raise QtRepoError('重置主仓库 失败: {}'.format(e))
            
            cmd = [self.git_exe, '-C', self.repo_path, 'submodule', 'foreach', '--recursive', 'git', 'reset', '--hard']
            try:
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
