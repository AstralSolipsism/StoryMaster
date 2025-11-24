"""
监控与调度组件实现
"""

import asyncio
import time
import uuid
import psutil
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum
import logging

from .interfaces import (
    IMonitoringScheduler, AgentTask, PerformanceMetrics,
    TaskPriority, ExecutionContext, IAgent
)

class SchedulingStrategy(Enum):
    """调度策略"""
    FIFO = "fifo"  # 先进先出
    PRIORITY = "priority"  # 优先级调度
    LOAD_BALANCE = "load_balance"  # 负载均衡
    ADAPTIVE = "adaptive"  # 自适应调度

@dataclass
class ScheduledTask:
    """调度任务"""
    task: AgentTask
    priority: TaskPriority
    task_id: str
    created_time: float
    scheduled_time: Optional[float] = None
    dependencies: List[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3

@dataclass
class LoadBalancingInfo:
    """负载均衡信息"""
    agent_id: str
    current_load: float
    capacity: float
    utilization_rate: float
    last_update: float

class PerformanceAnalyzer:
    """性能分析器"""
    
    def __init__(self):
        self.metrics_history: deque = deque(maxlen=1000)
        self.analysis_cache: Dict[str, Any] = {}
        self.cache_ttl = 60  # 缓存1分钟
        self.logger = logging.getLogger(__name__)
    
    async def analyze_performance(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """分析性能指标"""
        current_time = time.time()
        
        # 检查缓存
        if "analysis" in self.analysis_cache:
            cache_time, analysis = self.analysis_cache["analysis"]
            if current_time - cache_time < self.cache_ttl:
                return analysis
        
        # 添加到历史记录
        self.metrics_history.append({
            "timestamp": current_time,
            "metrics": metrics
        })
        
        # 执行分析
        analysis = {
            "timestamp": current_time,
            "trends": self._analyze_trends(),
            "bottlenecks": self._identify_bottlenecks(),
            "recommendations": self._generate_recommendations(metrics),
            "health_score": self._calculate_health_score(metrics)
        }
        
        # 更新缓存
        self.analysis_cache["analysis"] = (current_time, analysis)
        
        return analysis
    
    def _analyze_trends(self) -> Dict[str, str]:
        """分析趋势"""
        if len(self.metrics_history) < 10:
            return {"status": "insufficient_data"}
        
        recent_metrics = [entry["metrics"] for entry in list(self.metrics_history)[-10:]]
        
        # CPU趋势
        cpu_trend = self._calculate_trend([m.get("cpu_usage", 0) for m in recent_metrics])
        
        # 内存趋势
        memory_trend = self._calculate_trend([m.get("memory_usage", 0) for m in recent_metrics])
        
        # 响应时间趋势
        response_trend = self._calculate_trend([m.get("average_response_time", 0) for m in recent_metrics])
        
        return {
            "cpu_trend": cpu_trend,
            "memory_trend": memory_trend,
            "response_time_trend": response_trend
        }
    
    def _identify_bottlenecks(self) -> List[str]:
        """识别瓶颈"""
        if not self.metrics_history:
            return []
        
        latest_metrics = self.metrics_history[-1]["metrics"]
        bottlenecks = []
        
        # CPU瓶颈
        if latest_metrics.get("cpu_usage", 0) > 80:
            bottlenecks.append("CPU使用率过高")
        
        # 内存瓶颈
        if latest_metrics.get("memory_usage", 0) > 85:
            bottlenecks.append("内存使用率过高")
        
        # 响应时间瓶颈
        if latest_metrics.get("average_response_time", 0) > 5.0:
            bottlenecks.append("平均响应时间过长")
        
        # 失败率瓶颈
        completed_tasks = latest_metrics.get("completed_tasks", 0)
        failed_tasks = latest_metrics.get("failed_tasks", 0)
        total_tasks = completed_tasks + failed_tasks
        if total_tasks > 0:
            failure_rate = failed_tasks / total_tasks
            if failure_rate > 0.1:
                bottlenecks.append("任务失败率过高")
        
        return bottlenecks
    
    def _generate_recommendations(self, metrics: Dict[str, Any]) -> List[str]:
        """生成优化建议"""
        recommendations = []
        
        if metrics.get("cpu_usage", 0) > 70:
            recommendations.append("考虑增加CPU资源或优化计算密集型任务")
        
        if metrics.get("memory_usage", 0) > 75:
            recommendations.append("考虑增加内存或优化内存使用")
        
        if metrics.get("average_response_time", 0) > 3.0:
            recommendations.append("优化任务调度策略或增加并发处理能力")
        
        if metrics.get("active_tasks", 0) > 50:
            recommendations.append("考虑增加工作线程数或实现任务分片")
        
        return recommendations
    
    def _calculate_health_score(self, metrics: Dict[str, Any]) -> float:
        """计算健康分数"""
        score = 100.0
        
        # CPU影响
        cpu_impact = max(0, metrics.get("cpu_usage", 0) - 50) * 0.5
        score -= cpu_impact
        
        # 内存影响
        memory_impact = max(0, metrics.get("memory_usage", 0) - 60) * 0.4
        score -= memory_impact
        
        # 响应时间影响
        response_impact = max(0, metrics.get("average_response_time", 0) - 2.0) * 10
        score -= response_impact
        
        # 失败率影响
        completed_tasks = metrics.get("completed_tasks", 0)
        failed_tasks = metrics.get("failed_tasks", 0)
        total_tasks = completed_tasks + failed_tasks
        if total_tasks > 0:
            failure_rate = failed_tasks / total_tasks
            failure_impact = failure_rate * 30
            score -= failure_impact
        
        return max(0, min(100, score))
    
    def _calculate_trend(self, values: List[float]) -> str:
        """计算趋势"""
        if len(values) < 2:
            return "stable"
        
        # 简单线性回归
        n = len(values)
        x = list(range(n))
        sum_x = sum(x)
        sum_y = sum(values)
        sum_xy = sum(x[i] * values[i] for i in range(n))
        sum_x2 = sum(x[i] ** 2 for i in range(n))
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
        
        if abs(slope) < 0.1:
            return "stable"
        elif slope > 0:
            return "increasing"
        else:
            return "decreasing"

class TaskScheduler:
    """任务调度器"""
    
    def __init__(self, strategy: SchedulingStrategy = SchedulingStrategy.PRIORITY):
        self.strategy = strategy
        self.task_queues: Dict[TaskPriority, deque] = defaultdict(deque)
        self.scheduled_tasks: Dict[str, ScheduledTask] = {}
        self.load_balancer = LoadBalancer()
        self.logger = logging.getLogger(__name__)
    
    async def schedule_task(self, task: AgentTask, priority: TaskPriority = TaskPriority.NORMAL) -> str:
        """调度任务"""
        task_id = str(uuid.uuid4())
        
        scheduled_task = ScheduledTask(
            task=task,
            priority=priority,
            task_id=task_id,
            created_time=time.time()
        )
        
        # 根据策略调度
        if self.strategy == SchedulingStrategy.PRIORITY:
            self.task_queues[priority].append(scheduled_task)
        elif self.strategy == SchedulingStrategy.FIFO:
            self.task_queues[TaskPriority.NORMAL].append(scheduled_task)
        elif self.strategy == SchedulingStrategy.LOAD_BALANCE:
            await self._schedule_with_load_balance(scheduled_task)
        elif self.strategy == SchedulingStrategy.ADAPTIVE:
            await self._schedule_adaptive(scheduled_task)
        
        self.scheduled_tasks[task_id] = scheduled_task
        self.logger.info(f"任务 {task_id} 已调度，优先级: {priority.name}")
        
        return task_id
    
    async def get_next_task(self) -> Optional[ScheduledTask]:
        """获取下一个要执行的任务"""
        if self.strategy == SchedulingStrategy.PRIORITY:
            return self._get_next_priority_task()
        elif self.strategy == SchedulingStrategy.LOAD_BALANCE:
            return await self._get_load_balanced_task()
        elif self.strategy == SchedulingStrategy.ADAPTIVE:
            return await self._get_adaptive_task()
        else:
            return self._get_fifo_task()
    
    async def complete_task(self, task_id: str) -> None:
        """完成任务"""
        if task_id in self.scheduled_tasks:
            del self.scheduled_tasks[task_id]
            self.logger.info(f"任务 {task_id} 完成")
    
    async def fail_task(self, task_id: str, error: Exception) -> None:
        """任务失败"""
        if task_id in self.scheduled_tasks:
            scheduled_task = self.scheduled_tasks[task_id]
            scheduled_task.retry_count += 1
            
            if scheduled_task.retry_count < scheduled_task.max_retries:
                # 重新调度
                self.task_queues[scheduled_task.priority].append(scheduled_task)
                self.logger.warning(f"任务 {task_id} 失败，重试 {scheduled_task.retry_count}/{scheduled_task.max_retries}")
            else:
                # 达到最大重试次数
                del self.scheduled_tasks[task_id]
                self.logger.error(f"任务 {task_id} 达到最大重试次数，放弃")
    
    def _get_fifo_task(self) -> Optional[ScheduledTask]:
        """获取FIFO任务"""
        queue = self.task_queues[TaskPriority.NORMAL]
        return queue.popleft() if queue else None
    
    def _get_next_priority_task(self) -> Optional[ScheduledTask]:
        """获取下一个优先级任务"""
        # 按优先级顺序检查队列
        for priority in sorted(TaskPriority, key=lambda x: x.value, reverse=True):
            queue = self.task_queues[priority]
            if queue:
                return queue.popleft()
        
        return None
    
    async def _schedule_with_load_balance(self, task: ScheduledTask) -> None:
        """负载均衡调度"""
        # 选择负载最低的智能体
        best_agent = await self.load_balancer.get_best_agent()
        if best_agent:
            task.task.agent_id = best_agent
        self.task_queues[task.priority].append(task)
    
    async def _schedule_adaptive(self, task: ScheduledTask) -> None:
        """自适应调度"""
        # 根据系统状态动态选择策略
        cpu_usage = psutil.cpu_percent()
        
        if cpu_usage > 80:
            # 高负载时使用优先级调度
            self.task_queues[task.priority].append(task)
        else:
            # 正常负载时使用负载均衡
            await self._schedule_with_load_balance(task)
    
    async def _get_load_balanced_task(self) -> Optional[ScheduledTask]:
        """获取负载均衡任务"""
        best_agent = await self.load_balancer.get_best_agent()
        
        for priority in sorted(TaskPriority, key=lambda x: x.value, reverse=True):
            queue = self.task_queues[priority]
            if queue:
                task = queue.popleft()
                if best_agent:
                    task.task.agent_id = best_agent
                return task
        
        return None
    
    async def _get_adaptive_task(self) -> Optional[ScheduledTask]:
        """获取自适应任务"""
        # 根据当前系统状态选择任务
        cpu_usage = psutil.cpu_percent()
        
        if cpu_usage > 80:
            # 高负载时优先处理高优先级任务
            return self._get_next_priority_task()
        else:
            # 正常负载时使用负载均衡
            return await self._get_load_balanced_task()

class LoadBalancer:
    """负载均衡器"""
    
    def __init__(self):
        self.agent_loads: Dict[str, LoadBalancingInfo] = {}
        self.update_interval = 30  # 30秒更新一次
        self.last_update = 0
        self.logger = logging.getLogger(__name__)
    
    async def get_best_agent(self) -> Optional[str]:
        """获取最佳智能体"""
        current_time = time.time()
        
        # 定期更新负载信息
        if current_time - self.last_update > self.update_interval:
            await self._update_load_info()
            self.last_update = current_time
        
        if not self.agent_loads:
            return None
        
        # 选择利用率最低的智能体
        best_agent = min(
            self.agent_loads.items(),
            key=lambda x: x[1].utilization_rate
        )
        
        return best_agent[0]
    
    async def update_agent_load(self, agent_id: str, load: float, capacity: float) -> None:
        """更新智能体负载"""
        utilization = load / capacity if capacity > 0 else 1.0
        
        self.agent_loads[agent_id] = LoadBalancingInfo(
            agent_id=agent_id,
            current_load=load,
            capacity=capacity,
            utilization_rate=utilization,
            last_update=time.time()
        )
    
    async def _update_load_info(self) -> None:
        """更新负载信息"""
        # 清理过期的负载信息
        current_time = time.time()
        expired_agents = [
            agent_id for agent_id, info in self.agent_loads.items()
            if current_time - info.last_update > 300  # 5分钟
        ]
        
        for agent_id in expired_agents:
            del self.agent_loads[agent_id]
        
        if expired_agents:
            self.logger.debug(f"清理了 {len(expired_agents)} 个过期的负载信息")

class MonitoringScheduler(IMonitoringScheduler):
    """监控与调度器实现"""
    
    def __init__(self, scheduling_strategy: SchedulingStrategy = SchedulingStrategy.PRIORITY):
        self.performance_analyzer = PerformanceAnalyzer()
        self.task_scheduler = TaskScheduler(scheduling_strategy)
        self.metrics_collectors: List[Callable] = []
        self.running = False
        self.monitoring_task: Optional[asyncio.Task] = None
        self.logger = logging.getLogger(__name__)
    
    async def start(self) -> None:
        """启动监控调度器"""
        if self.running:
            return
        
        self.running = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        self.logger.info("监控调度器启动")
    
    async def stop(self) -> None:
        """停止监控调度器"""
        if not self.running:
            return
        
        self.running = False
        
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("监控调度器停止")
    
    async def collect_metrics(self) -> Dict[str, Any]:
        """收集指标"""
        metrics = {
            "system": {
                "cpu_usage": psutil.cpu_percent(),
                "memory_usage": psutil.virtual_memory().percent,
                "disk_usage": psutil.disk_usage('/').percent,
                "network_io": psutil.net_io_counters()._asdict() if psutil.net_io_counters() else {}
            },
            "scheduler": {
                "pending_tasks": sum(len(queue) for queue in self.task_scheduler.task_queues.values()),
                "active_tasks": len(self.task_scheduler.scheduled_tasks),
                "strategy": self.task_scheduler.strategy.value
            },
            "load_balancer": {
                "agent_count": len(self.task_scheduler.load_balancer.agent_loads),
                "average_utilization": self._calculate_average_utilization()
            }
        }
        
        # 调用自定义指标收集器
        for collector in self.metrics_collectors:
            try:
                custom_metrics = await collector()
                metrics.update(custom_metrics)
            except Exception as e:
                self.logger.error(f"指标收集器错误: {e}")
        
        return metrics
    
    async def analyze_performance(self, metrics: Dict[str, Any]) -> Any:
        """分析性能"""
        return await self.performance_analyzer.analyze_performance(metrics)
    
    async def schedule_task(self, task: AgentTask, priority: TaskPriority = TaskPriority.NORMAL) -> str:
        """调度任务"""
        return await self.task_scheduler.schedule_task(task, priority)
    
    async def get_scheduling_status(self) -> Dict[str, Any]:
        """获取调度状态"""
        return {
            "strategy": self.task_scheduler.strategy.value,
            "pending_tasks": {
                priority.name: len(queue) 
                for priority, queue in self.task_scheduler.task_queues.items()
            },
            "active_tasks": len(self.task_scheduler.scheduled_tasks),
            "load_balancer": {
                agent_id: info.utilization_rate
                for agent_id, info in self.task_scheduler.load_balancer.agent_loads.items()
            }
        }
    
    def add_metrics_collector(self, collector: Callable) -> None:
        """添加指标收集器"""
        self.metrics_collectors.append(collector)
    
    async def _monitoring_loop(self) -> None:
        """监控循环"""
        while self.running:
            try:
                # 收集指标
                metrics = await self.collect_metrics()
                
                # 分析性能
                analysis = await self.analyze_performance(metrics)
                
                # 记录关键指标
                if analysis["health_score"] < 70:
                    self.logger.warning(f"系统健康分数较低: {analysis['health_score']}")
                
                if analysis["bottlenecks"]:
                    self.logger.warning(f"检测到瓶颈: {analysis['bottlenecks']}")
                
                await asyncio.sleep(30)  # 每30秒监控一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"监控循环错误: {e}")
                await asyncio.sleep(5)
    
    def _calculate_average_utilization(self) -> float:
        """计算平均利用率"""
        if not self.task_scheduler.load_balancer.agent_loads:
            return 0.0
        
        total_utilization = sum(
            info.utilization_rate 
            for info in self.task_scheduler.load_balancer.agent_loads.values()
        )
        
        return total_utilization / len(self.task_scheduler.load_balancer.agent_loads)

# 全局监控调度器实例
monitoring_scheduler = MonitoringScheduler()

# 便捷函数
async def get_monitoring_scheduler() -> MonitoringScheduler:
    """获取监控调度器实例"""
    if not monitoring_scheduler.running:
        await monitoring_scheduler.start()
    return monitoring_scheduler

async def create_monitoring_scheduler(strategy: SchedulingStrategy = SchedulingStrategy.PRIORITY) -> MonitoringScheduler:
    """创建新的监控调度器实例"""
    scheduler = MonitoringScheduler(strategy)
    await scheduler.start()
    return scheduler