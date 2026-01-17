"""
Unit tests for horizontal scaling components
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from typing import Dict, Any
from app.scaling.consistent_hash_manager import ConsistentHashManager
from app.scaling.backpressure_monitor import BackpressureMonitor, BackpressureLevel
from test.stubs.docker_orchestrator import DockerOrchestrator


def build_metrics(
    queue_depth: int,
    p99_latency: float = 1000.0,
    cpu_usage: float = 0.2,
    memory_usage: float = 0.2,
    error_rate: float = 0.0
) -> Dict[str, Any]:
    """Helper to build metrics payloads for backpressure tests."""
    return {
        "queue_depth": queue_depth,
        "p99_latency": p99_latency,
        "cpu_usage": cpu_usage,
        "memory_usage": memory_usage,
        "error_rate": error_rate
    }

@pytest.mark.unit
class TestConsistentHashManager:
    """Test suite for ConsistentHashManager"""
    
    @pytest.fixture
    def hash_manager(self):
        """Create ConsistentHashManager with test configuration"""
        return ConsistentHashManager(virtual_nodes=150)
    
    def test_initialization(self, hash_manager):
        """Test proper initialization"""
        assert hash_manager.virtual_nodes == 150
        assert isinstance(hash_manager.ring, dict)
        assert len(hash_manager.nodes) == 0
    
    def test_add_node(self, hash_manager):
        """Test adding nodes to the ring"""
        # Add first node
        hash_manager.add_node('signal-service-1')
        assert 'signal-service-1' in hash_manager.nodes
        assert len(hash_manager.ring) == 150  # virtual_nodes
        
        # Add second node
        hash_manager.add_node('signal-service-2')
        assert 'signal-service-2' in hash_manager.nodes
        assert len(hash_manager.ring) == 300  # 2 * virtual_nodes
        
        # Verify distribution
        node_counts = {}
        for node in hash_manager.ring.values():
            node_counts[node] = node_counts.get(node, 0) + 1
        
        assert node_counts['signal-service-1'] == 150
        assert node_counts['signal-service-2'] == 150
    
    def test_remove_node(self, hash_manager):
        """Test removing nodes from the ring"""
        # Add nodes
        hash_manager.add_node('signal-service-1')
        hash_manager.add_node('signal-service-2')
        
        # Remove one node
        hash_manager.remove_node('signal-service-1')
        assert 'signal-service-1' not in hash_manager.nodes
        assert 'signal-service-2' in hash_manager.nodes
        assert len(hash_manager.ring) == 150
        
        # All ring entries should point to remaining node
        for node in hash_manager.ring.values():
            assert node == 'signal-service-2'
    
    def test_get_node_for_instrument(self, hash_manager):
        """Test instrument to node assignment"""
        # Add nodes
        hash_manager.add_node('signal-service-1')
        hash_manager.add_node('signal-service-2')
        hash_manager.add_node('signal-service-3')
        
        # Test consistent assignment
        instruments = [
            'NSE@NIFTY@equity_options@2025-07-10@call@21500',
            'NSE@BANKNIFTY@equity_options@2025-07-10@call@45000',
            'NSE@RELIANCE@equity_spot',
            'NSE@TCS@equity_spot'
        ]
        
        assignments = {}
        for instrument in instruments:
            node = hash_manager.get_node_for_instrument(instrument)
            assignments[instrument] = node
            assert node in hash_manager.nodes
        
        # Test consistency - multiple calls should return same node
        for instrument in instruments:
            node = hash_manager.get_node_for_instrument(instrument)
            assert node == assignments[instrument]
    
    def test_load_distribution(self, hash_manager):
        """Test even load distribution across nodes"""
        # Add 3 nodes
        nodes = ['signal-service-1', 'signal-service-2', 'signal-service-3']
        for node in nodes:
            hash_manager.add_node(node)
        
        # Test with many instruments
        node_counts = {node: 0 for node in nodes}
        
        for i in range(1000):
            instrument = f'NSE@TEST{i}@equity_spot'
            node = hash_manager.get_node_for_instrument(instrument)
            node_counts[node] += 1
        
        # Distribution should be relatively even (within 20% of average)
        average = 1000 / 3
        for count in node_counts.values():
            assert abs(count - average) / average < 0.2
    
    def test_node_failure_handling(self, hash_manager):
        """Test handling of node failures"""
        # Add nodes
        hash_manager.add_node('signal-service-1')
        hash_manager.add_node('signal-service-2')
        hash_manager.add_node('signal-service-3')
        
        # Get assignments before failure
        instruments = [f'NSE@TEST{i}@equity_spot' for i in range(100)]
        before_assignments = {}
        for instrument in instruments:
            before_assignments[instrument] = hash_manager.get_node_for_instrument(instrument)
        
        # Remove one node (simulate failure)
        hash_manager.remove_node('signal-service-2')
        
        # Check reassignments
        after_assignments = {}
        for instrument in instruments:
            after_assignments[instrument] = hash_manager.get_node_for_instrument(instrument)
        
        # Only instruments previously on failed node should be reassigned
        reassigned_count = 0
        for instrument in instruments:
            if before_assignments[instrument] == 'signal-service-2':
                assert after_assignments[instrument] in ['signal-service-1', 'signal-service-3']
                reassigned_count += 1
            else:
                assert before_assignments[instrument] == after_assignments[instrument]
        
        assert reassigned_count > 0  # Some instruments should have been reassigned
    
    def test_performance_requirements(self, hash_manager):
        """Test that lookups meet performance requirements"""
        import time
        
        # Add nodes
        for i in range(5):
            hash_manager.add_node(f'signal-service-{i}')
        
        # Test lookup performance
        instruments = [f'NSE@TEST{i}@equity_spot' for i in range(1000)]
        
        start = time.time()
        for instrument in instruments:
            hash_manager.get_node_for_instrument(instrument)
        end = time.time()
        
        avg_time = (end - start) / 1000 * 1000  # Convert to ms
        assert avg_time < 0.1, f"Average lookup time {avg_time:.3f}ms exceeds 0.1ms requirement"


@pytest.mark.unit
class TestBackpressureMonitor:
    """Test suite for BackpressureMonitor"""
    
    @pytest.fixture
    def monitor(self):
        """Create BackpressureMonitor instance"""
        return BackpressureMonitor()
    
    def test_initialization(self, monitor):
        """Test proper initialization"""
        assert monitor.current_backpressure == BackpressureLevel.LOW
        assert len(monitor.metrics_history) == 0
        assert monitor.last_recommendation is None
    
    def test_backpressure_level_calculation(self, monitor):
        """Test backpressure level calculation from metrics"""
        monitor.update_metrics("pod-1", build_metrics(queue_depth=100))
        assert monitor.current_backpressure == BackpressureLevel.LOW
        
        monitor.update_metrics(
            "pod-1",
            build_metrics(queue_depth=800, cpu_usage=0.7, memory_usage=0.75)
        )
        assert monitor.current_backpressure == BackpressureLevel.MEDIUM
        
        monitor.update_metrics(
            "pod-1",
            build_metrics(queue_depth=1500, cpu_usage=0.85, memory_usage=0.85)
        )
        assert monitor.current_backpressure == BackpressureLevel.HIGH
        
        monitor.update_metrics(
            "pod-1",
            build_metrics(queue_depth=2500, cpu_usage=0.96, memory_usage=0.96)
        )
        assert monitor.current_backpressure == BackpressureLevel.CRITICAL
    
    def test_metrics_history(self, monitor):
        """Test metrics history tracking"""
        # Update metrics multiple times
        for i in range(10):
            monitor.update_metrics(
                "pod-1",
                build_metrics(
                    queue_depth=100 + i * 50,
                    cpu_usage=0.2 + i * 0.01,
                    memory_usage=0.3 + i * 0.01,
                    error_rate=0.01
                )
            )
        
        # Should track history
        assert len(monitor.metrics_history) == 10
        
        # Latest entry should match current values
        latest = monitor.metrics_history[-1]
        assert latest['queue_depth'] == 550
        assert latest['cpu_usage'] == pytest.approx(0.29)
        assert latest['memory_usage'] == pytest.approx(0.39)
    
    def test_trend_analysis(self, monitor):
        """Test backpressure trend analysis"""
        # Increasing trend
        for i in range(5):
            monitor.update_metrics(
                "pod-1",
                build_metrics(queue_depth=200 + i * 200, cpu_usage=0.2, memory_usage=0.2)
            )
        
        trend = monitor._analyze_trends()
        assert trend['trend'] == 'increasing'
        
        # Decreasing trend
        monitor.metrics_history = []
        for i in range(5):
            monitor.update_metrics(
                "pod-1",
                build_metrics(queue_depth=1000 - i * 150, cpu_usage=0.2, memory_usage=0.2)
            )
        
        trend = monitor._analyze_trends()
        assert trend['trend'] == 'decreasing'
    
    def test_scaling_recommendations(self, monitor):
        """Test scaling recommendations based on backpressure"""
        monitor.recommendation_cooldown = 0
        
        # Low backpressure - no scaling needed
        monitor.update_metrics("pod-1", build_metrics(queue_depth=100))
        recommendations = monitor.get_scaling_recommendation(current_pods=2)
        assert recommendations.action == 'none'
        
        # High backpressure - scale up
        monitor.update_metrics("pod-1", build_metrics(queue_depth=1500, cpu_usage=0.9))
        recommendations = monitor.get_scaling_recommendation(current_pods=1)
        assert recommendations.action == 'scale_up'
        assert recommendations.recommended_pods > 1
        
        # Critical backpressure - urgent scaling
        monitor.update_metrics(
            "pod-1",
            build_metrics(queue_depth=3000, cpu_usage=0.96, memory_usage=0.96, error_rate=0.3)
        )
        recommendations = monitor.get_scaling_recommendation(current_pods=2)
        assert recommendations.action == 'scale_up'
        assert recommendations.urgency == 'critical'


@pytest.mark.unit
class TestDockerOrchestrator:
    """Test suite for DockerOrchestrator"""
    
    @pytest.fixture
    def orchestrator(self):
        """Create DockerOrchestrator instance"""
        return DockerOrchestrator()
    
    @pytest.mark.asyncio
    async def test_scaling_decision_logic(self, orchestrator):
        """Test scaling decision logic"""
        current_replicas = 2
        
        # No scaling needed
        recommendations = {
            'action': 'none',
            'target_replicas': 2,
            'urgency': 'low'
        }
        decision = await orchestrator._make_scaling_decision(current_replicas, recommendations)
        assert decision['scale'] == False
        
        # Scale up needed
        recommendations = {
            'action': 'scale_up',
            'target_replicas': 4,
            'urgency': 'high'
        }
        decision = await orchestrator._make_scaling_decision(current_replicas, recommendations)
        assert decision['scale'] == True
        assert decision['target_replicas'] == 4
        assert decision['direction'] == 'up'
        
        # Scale down needed
        recommendations = {
            'action': 'scale_down',
            'target_replicas': 1,
            'urgency': 'low'
        }
        decision = await orchestrator._make_scaling_decision(current_replicas, recommendations)
        assert decision['scale'] == True
        assert decision['target_replicas'] == 1
        assert decision['direction'] == 'down'
    
    @pytest.mark.asyncio
    async def test_replica_limit_enforcement(self, orchestrator):
        """Test replica limit enforcement"""
        # Test maximum replica limit
        recommendations = {
            'action': 'scale_up',
            'target_replicas': 15,  # Above max limit (10)
            'urgency': 'critical'
        }
        decision = await orchestrator._make_scaling_decision(2, recommendations)
        assert decision['target_replicas'] <= 10
        
        # Test minimum replica limit
        recommendations = {
            'action': 'scale_down',
            'target_replicas': 0,  # Below min limit (1)
            'urgency': 'low'
        }
        decision = await orchestrator._make_scaling_decision(3, recommendations)
        assert decision['target_replicas'] >= 1
    
    @pytest.mark.asyncio
    async def test_scaling_cooldown(self, orchestrator):
        """Test scaling cooldown mechanism"""
        import time
        
        # Record recent scaling
        orchestrator.last_scaling_time = time.time()
        
        recommendations = {
            'action': 'scale_up',
            'target_replicas': 4,
            'urgency': 'medium'
        }
        
        # Should respect cooldown for non-critical events
        decision = await orchestrator._make_scaling_decision(2, recommendations)
        assert decision['scale'] == False
        assert 'cooldown' in decision['reason']
        
        # Critical events should override cooldown
        recommendations['urgency'] = 'critical'
        decision = await orchestrator._make_scaling_decision(2, recommendations)
        assert decision['scale'] == True
    
    @pytest.mark.asyncio
    async def test_health_check_integration(self, orchestrator):
        """Test health check integration with scaling decisions"""
        with patch.object(orchestrator, '_check_instance_health') as mock_health:
            # All instances healthy
            mock_health.return_value = {'healthy': True, 'response_time': 50}
            
            health_status = await orchestrator._get_cluster_health()
            assert health_status['overall_health'] > 0.8
            
            # Some instances unhealthy
            mock_health.side_effect = [
                {'healthy': True, 'response_time': 50},
                {'healthy': False, 'response_time': 5000},
                {'healthy': True, 'response_time': 75}
            ]
            
            health_status = await orchestrator._get_cluster_health()
            assert health_status['overall_health'] < 1.0
            assert health_status['unhealthy_instances'] == 1
    
    @pytest.mark.asyncio
    async def test_graceful_shutdown_handling(self, orchestrator):
        """Test graceful shutdown of instances during scale down"""
        with patch.object(orchestrator, '_send_shutdown_signal') as mock_shutdown, \
             patch.object(orchestrator, '_wait_for_graceful_shutdown') as mock_wait, \
             patch.object(orchestrator, '_force_stop_container') as mock_force:
            
            # Successful graceful shutdown
            mock_wait.return_value = True
            
            result = await orchestrator._shutdown_instance('signal-service-3')
            assert result == True
            mock_shutdown.assert_called_once()
            mock_wait.assert_called_once()
            mock_force.assert_not_called()
            
            # Graceful shutdown timeout
            mock_wait.return_value = False
            
            result = await orchestrator._shutdown_instance('signal-service-3')
            mock_force.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_load_balancer_integration(self, orchestrator):
        """Test load balancer integration during scaling"""
        with patch.object(orchestrator, '_register_with_load_balancer') as mock_register, \
             patch.object(orchestrator, '_deregister_from_load_balancer') as mock_deregister:
            
            # Scale up - should register new instances
            await orchestrator._handle_scale_up(2, 4)
            assert mock_register.call_count == 2  # 2 new instances
            
            # Scale down - should deregister instances
            await orchestrator._handle_scale_down(4, 2)
            assert mock_deregister.call_count == 2  # 2 removed instances
    
    @pytest.mark.asyncio
    async def test_error_handling_during_scaling(self, orchestrator):
        """Test error handling during scaling operations"""
        with patch.object(orchestrator, '_start_new_instance') as mock_start:
            # Simulate container start failure
            mock_start.side_effect = Exception("Docker daemon error")
            
            result = await orchestrator._handle_scale_up(2, 4)
            assert result['success'] == False
            assert 'error' in result
            
            # Should attempt rollback on partial failure
            mock_start.side_effect = [
                'signal-service-3',  # Success
                Exception("Network error")  # Failure
            ]
            
            with patch.object(orchestrator, '_cleanup_failed_scaling') as mock_cleanup:
                result = await orchestrator._handle_scale_up(2, 4)
                mock_cleanup.assert_called()
    
    @pytest.mark.asyncio
    async def test_monitoring_integration(self, orchestrator):
        """Test monitoring and metrics integration"""
        with patch.object(orchestrator, '_emit_scaling_metrics') as mock_metrics:
            scaling_decision = {
                'scale': True,
                'direction': 'up',
                'target_replicas': 4,
                'reason': 'high_backpressure'
            }
            
            await orchestrator._execute_scaling_decision(scaling_decision)
            
            # Should emit metrics for scaling events
            mock_metrics.assert_called()
            call_args = mock_metrics.call_args[0][0]
            assert call_args['event_type'] == 'scaling_initiated'
            assert call_args['direction'] == 'up'
            assert call_args['target_replicas'] == 4
