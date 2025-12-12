"""
文件系统适配器实现

提供文件系统的读写操作功能。
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
import aiofiles
import aiofiles.os

from ..interfaces import IFileStorage


class FileSystemAdapter(IFileStorage):
    """文件系统适配器"""
    
    def __init__(self, base_path: str = "./data", create_if_missing: bool = True):
        """
        初始化文件系统适配器
        
        Args:
            base_path: 基础路径
            create_if_missing: 如果路径不存在是否创建
        """
        self.base_path = Path(base_path).resolve()
        self.create_if_missing = create_if_missing
        self.logger = logging.getLogger(__name__)
        
        # 确保基础路径存在
        if self.create_if_missing:
            self.base_path.mkdir(parents=True, exist_ok=True)
    
    async def read_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """读取文件"""
        try:
            full_path = self._get_full_path(file_path)
            
            # 检查文件是否存在
            if not await aiofiles.os.path.exists(full_path):
                self.logger.warning(f"文件不存在: {full_path}")
                return None
            
            # 异步读取文件
            async with aiofiles.open(full_path, 'r', encoding='utf-8') as file:
                content = await file.read()
                return json.loads(content)
                
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self.logger.error(f"解析文件内容时发生错误: {e}")
            return None
        except Exception as e:
            self.logger.error(f"读取文件时发生错误: {e}")
            return None
    
    async def write_file(self, file_path: str, data: Dict[str, Any]) -> bool:
        """写入文件"""
        try:
            full_path = self._get_full_path(file_path)
            
            # 确保目录存在
            await self._ensure_directory_exists(full_path.parent)
            
            # 序列化数据
            content = json.dumps(data, ensure_ascii=False, indent=2, default=str)
            
            # 异步写入文件
            async with aiofiles.open(full_path, 'w', encoding='utf-8') as file:
                await file.write(content)
            
            self.logger.debug(f"成功写入文件: {full_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"写入文件时发生错误: {e}")
            return False
    
    async def delete_file(self, file_path: str) -> bool:
        """删除文件"""
        try:
            full_path = self._get_full_path(file_path)
            
            # 检查文件是否存在
            if not await aiofiles.os.path.exists(full_path):
                self.logger.warning(f"文件不存在，无需删除: {full_path}")
                return True
            
            # 异步删除文件
            await aiofiles.os.remove(full_path)
            
            self.logger.debug(f"成功删除文件: {full_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"删除文件时发生错误: {e}")
            return False
    
    async def list_files(self, directory: str, pattern: str = "*") -> List[str]:
        """列出目录中的文件"""
        try:
            full_path = self._get_full_path(directory)
            
            # 检查目录是否存在
            if not await aiofiles.os.path.exists(full_path):
                self.logger.warning(f"目录不存在: {full_path}")
                return []
            
            # 检查是否为目录
            if not await aiofiles.os.path.isdir(full_path):
                self.logger.warning(f"路径不是目录: {full_path}")
                return []
            
            # 异步列出文件
            files = []
            entries = await aiofiles.os.scandir(full_path)
            for entry in entries:
                if entry.is_file():
                    # 简单的模式匹配
                    if self._match_pattern(entry.name, pattern):
                        files.append(entry.name)
            
            return files
            
        except Exception as e:
            self.logger.error(f"列出文件时发生错误: {e}")
            return []
    
    async def exists(self, file_path: str) -> bool:
        """检查文件是否存在"""
        try:
            full_path = self._get_full_path(file_path)
            return await aiofiles.os.path.exists(full_path)
            
        except Exception as e:
            self.logger.error(f"检查文件是否存在时发生错误: {e}")
            return False
    
    async def create_directory(self, directory: str) -> bool:
        """创建目录"""
        try:
            full_path = self._get_full_path(directory)
            await aiofiles.os.makedirs(full_path, exist_ok=True)
            self.logger.debug(f"成功创建目录: {full_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"创建目录时发生错误: {e}")
            return False
    
    async def delete_directory(self, directory: str, recursive: bool = False) -> bool:
        """删除目录"""
        try:
            full_path = self._get_full_path(directory)
            
            if not await aiofiles.os.path.exists(full_path):
                self.logger.warning(f"目录不存在，无需删除: {full_path}")
                return True
            
            if recursive:
                # 使用异步方式递归删除目录，避免阻塞事件循环
                import asyncio
                import os
                import shutil
                
                loop = asyncio.get_event_loop()
                
                def _recursive_delete():
                    shutil.rmtree(full_path)
                
                await loop.run_in_executor(None, _recursive_delete)
            else:
                    await aiofiles.os.rmdir(full_path)
            
            self.logger.debug(f"成功删除目录: {full_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"删除目录时发生错误: {e}")
            return False
    
    async def copy_file(self, source_path: str, destination_path: str) -> bool:
        """复制文件"""
        try:
            full_source_path = self._get_full_path(source_path)
            full_dest_path = self._get_full_path(destination_path)
            
            # 确保目标目录存在
            await self._ensure_directory_exists(full_dest_path.parent)
            
            # 异步复制文件
            async with aiofiles.open(full_source_path, 'rb') as source_file:
                async with aiofiles.open(full_dest_path, 'wb') as dest_file:
                    while True:
                        chunk = await source_file.read(8192)  # 8KB chunks
                        if not chunk:
                            break
                        await dest_file.write(chunk)
            
            self.logger.debug(f"成功复制文件: {full_source_path} -> {full_dest_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"复制文件时发生错误: {e}")
            return False
    
    async def move_file(self, source_path: str, destination_path: str) -> bool:
        """移动文件"""
        try:
            full_source_path = self._get_full_path(source_path)
            full_dest_path = self._get_full_path(destination_path)
            
            # 确保目标目录存在
            await self._ensure_directory_exists(full_dest_path.parent)
            
            # 异步移动文件
            await aiofiles.os.rename(full_source_path, full_dest_path)
            
            self.logger.debug(f"成功移动文件: {full_source_path} -> {full_dest_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"移动文件时发生错误: {e}")
            return False
    
    async def get_file_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        """获取文件信息"""
        try:
            full_path = self._get_full_path(file_path)
            
            if not await aiofiles.os.path.exists(full_path):
                return None
            
            stat = await aiofiles.os.stat(full_path)
            
            return {
                "path": str(full_path),
                "size": stat.st_size,
                "created_time": stat.st_ctime,
                "modified_time": stat.st_mtime,
                "is_file": await aiofiles.os.path.isfile(full_path),
                "is_directory": await aiofiles.os.path.isdir(full_path)
            }
            
        except Exception as e:
            self.logger.error(f"获取文件信息时发生错误: {e}")
            return None
    
    async def get_directory_size(self, directory: str) -> int:
        """获取目录大小"""
        try:
            full_path = self._get_full_path(directory)
            total_size = 0
            
            # 使用异步方式遍历目录，避免阻塞事件循环
            import asyncio
            import os
            
            # 使用run_in_executor将同步操作移到线程池中执行
            loop = asyncio.get_event_loop()
            
            def _calculate_size():
                size = 0
                for root, dirs, files in os.walk(full_path):
                    for file in files:
                        file_path = Path(root) / file
                        if os.path.isfile(file_path):
                            stat = os.stat(file_path)
                            size += stat.st_size
                return size
            
            total_size = await loop.run_in_executor(None, _calculate_size)
            return total_size
            
        except Exception as e:
            self.logger.error(f"获取目录大小时发生错误: {e}")
            return 0
    
    def _get_full_path(self, file_path: str) -> Path:
        """获取完整路径，防止路径遍历攻击"""
        # 规范化路径，解析任何..或.组件
        normalized_path = Path(file_path).as_posix()
        
        # 检查是否包含路径遍历字符
        if '..' in normalized_path or normalized_path.startswith('/'):
            self.logger.warning(f"检测到潜在路径遍历攻击: {file_path}")
            raise ValueError(f"不安全的路径: {file_path}")
        
        # 始终返回相对于base_path的路径
        return (self.base_path / file_path).resolve()
    
    async def _ensure_directory_exists(self, directory: Path) -> None:
        """确保目录存在"""
        if not await aiofiles.os.path.exists(directory):
            await aiofiles.os.makedirs(directory, exist_ok=True)
    
    def _match_pattern(self, filename: str, pattern: str) -> bool:
        """简单的模式匹配"""
        import fnmatch
        return fnmatch.fnmatch(filename, pattern)
    
    async def backup_file(self, file_path: str, backup_suffix: str = ".bak") -> bool:
        """备份文件"""
        try:
            full_path = self._get_full_path(file_path)
            backup_path = full_path.with_suffix(full_path.suffix + backup_suffix)
            
            # 检查原文件是否存在
            if not await aiofiles.os.path.exists(full_path):
                self.logger.warning(f"原文件不存在，无需备份: {full_path}")
                return False
            
            # 复制文件作为备份
            return await self.copy_file(str(full_path), str(backup_path))
            
        except Exception as e:
            self.logger.error(f"备份文件时发生错误: {e}")
            return False
    
    async def restore_file(self, backup_path: str, target_path: str) -> bool:
        """恢复文件"""
        try:
            return await self.copy_file(backup_path, target_path)
            
        except Exception as e:
            self.logger.error(f"恢复文件时发生错误: {e}")
            return False
    
    async def cleanup_old_files(self, directory: str, days: int = 30, pattern: str = "*.bak") -> int:
        """清理旧文件"""
        try:
            import time
            full_path = self._get_full_path(directory)
            current_time = time.time()
            cutoff_time = current_time - (days * 24 * 60 * 60)
            
            deleted_count = 0
            files = await self.list_files(directory, pattern)
            
            for file in files:
                file_path = full_path / file
                stat = await aiofiles.os.stat(file_path)
                
                if stat.st_mtime < cutoff_time:
                    await aiofiles.os.remove(file_path)
                    deleted_count += 1
                    self.logger.debug(f"删除旧文件: {file_path}")
            
            self.logger.info(f"清理完成，删除了 {deleted_count} 个旧文件")
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"清理旧文件时发生错误: {e}")
            return 0