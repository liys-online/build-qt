"""commit_hash_fetcher.py

Utility to fetch the latest commit hash from a remote Git repository.

Features:
- Fetch latest commit hash from a remote repository
- Support both GitCode and GitHub URLs
- Update local commit_hash file
"""
import subprocess
import os
from typing import Optional


class CommitHashFetcherError(Exception):
    """Exception raised for errors in the CommitHashFetcher."""
    pass


class CommitHashFetcher:
    """Fetch and manage commit hashes from remote Git repositories.
    
    Parameters:
    - repo_url: URL of the remote Git repository
    - commit_hash_file: Path to the file where commit hash will be stored
    """
    
    def __init__(self, repo_url: str, commit_hash_file: str, git_exe: Optional[str] = None):
        self.repo_url = repo_url
        self.commit_hash_file = commit_hash_file
        
        # Find git executable
        if git_exe:
            self.git_exe = git_exe
        else:
            import shutil
            self.git_exe = shutil.which('git')
            if not self.git_exe:
                raise CommitHashFetcherError('Git executable not found in system PATH')
    
    def fetch_latest_commit_hash(self, branch: str = 'HEAD') -> str:
        """Fetch the latest commit hash from the remote repository.
        
        Parameters:
        - branch: Branch or ref to fetch (default: HEAD for the default branch)
        
        Returns:
        - The commit hash as a string
        """
        try:
            # Use git ls-remote to fetch the latest commit hash without cloning
            cmd = [self.git_exe, 'ls-remote', self.repo_url, branch]
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Parse the output - format is "hash\tref"
            output = result.stdout.strip()
            if not output:
                raise CommitHashFetcherError(f'No output from git ls-remote for {self.repo_url}')
            
            # Get the first line and extract the hash
            first_line = output.split('\n')[0]
            commit_hash = first_line.split('\t')[0].strip()
            
            if not commit_hash or len(commit_hash) != 40:
                raise CommitHashFetcherError(f'Invalid commit hash format: {commit_hash}')
            
            return commit_hash
            
        except subprocess.TimeoutExpired:
            raise CommitHashFetcherError(f'Timeout while fetching commit hash from {self.repo_url}')
        except subprocess.CalledProcessError as e:
            raise CommitHashFetcherError(
                f'Failed to fetch commit hash from {self.repo_url}: {e.stderr}'
            )
        except Exception as e:
            raise CommitHashFetcherError(f'Error fetching commit hash: {str(e)}')
    
    def update_commit_hash_file(self, commit_hash: Optional[str] = None) -> str:
        """Update the commit_hash file with the latest commit hash.
        
        Parameters:
        - commit_hash: If provided, use this hash; otherwise fetch the latest
        
        Returns:
        - The commit hash that was written to the file
        """
        if commit_hash is None:
            commit_hash = self.fetch_latest_commit_hash()
        
        try:
            # Write the commit hash to the file
            with open(self.commit_hash_file, 'w') as f:
                f.write(commit_hash + '\n')
            
            print(f'Updated {self.commit_hash_file} with commit hash: {commit_hash}')
            return commit_hash
            
        except IOError as e:
            raise CommitHashFetcherError(f'Failed to write to {self.commit_hash_file}: {str(e)}')
    
    def read_commit_hash_file(self) -> Optional[str]:
        """Read the current commit hash from the file.
        
        Returns:
        - The commit hash or None if file doesn't exist or is empty
        """
        if not os.path.exists(self.commit_hash_file):
            return None
        
        try:
            with open(self.commit_hash_file, 'r') as f:
                content = f.read().strip()
                return content if content else None
        except IOError:
            return None


if __name__ == '__main__':
    print('This module provides CommitHashFetcher class for fetching commit hashes from remote Git repositories')
