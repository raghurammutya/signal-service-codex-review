#!/usr/bin/env python3
"""
Phase 0 Checklist Generator

Generates detailed checklists for Phase 0 execution based on token usage scan results
and creates measurable migration tasks.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any
from dataclasses import dataclass
from pathlib import Path

@dataclass
class MigrationTask:
    """Individual migration task definition"""
    task_id: str
    title: str
    description: str
    service: str
    priority: str  # critical, high, medium, low
    estimated_hours: int
    dependencies: List[str]
    acceptance_criteria: List[str]
    assignee: str = ""
    status: str = "pending"

class Phase0ChecklistGenerator:
    """Generates comprehensive Phase 0 execution checklists"""
    
    def __init__(self, token_inventory_file: str):
        self.inventory_data = self._load_inventory_data(token_inventory_file)
        self.tasks: List[MigrationTask] = []
        self.checklist_sections = {}
        
    def _load_inventory_data(self, inventory_file: str) -> Dict[str, Any]:
        """Load token usage inventory data"""
        try:
            with open(inventory_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ Token inventory file not found: {inventory_file}")
            return {}
    
    def generate_complete_checklist(self) -> Dict[str, Any]:
        """Generate complete Phase 0 execution checklist"""
        
        # Generate all checklist sections
        sections_raw = {
            "audit_tasks": self._generate_audit_tasks(),
            "contract_definition_tasks": self._generate_contract_tasks(),
            "documentation_tasks": self._generate_documentation_tasks(),
            "testing_framework_tasks": self._generate_testing_tasks(),
            "governance_tasks": self._generate_governance_tasks()
        }
        
        # Convert sections to serializable format
        self.checklist_sections = {
            section_name: [self._task_to_dict(task) for task in tasks]
            for section_name, tasks in sections_raw.items()
        }
        
        # Combine all tasks (already in dict format)
        all_tasks = []
        for section_tasks in self.checklist_sections.values():
            all_tasks.extend(section_tasks)
        
        # Generate timeline using original task objects
        original_tasks = []
        for section_tasks in sections_raw.values():
            original_tasks.extend(section_tasks)
        timeline = self._generate_timeline(original_tasks)
        
        return {
            "phase": "Phase 0: Token Usage Audit & Contract Enforcement",
            "duration": "1 week",
            "generated_at": datetime.now().isoformat(),
            "inventory_summary": self._generate_inventory_summary(),
            "task_sections": self.checklist_sections,
            "all_tasks": all_tasks,
            "timeline": timeline,
            "success_criteria": self._define_success_criteria()
        }
    
    def _generate_audit_tasks(self) -> List[MigrationTask]:
        """Generate token usage audit tasks"""
        tasks = []
        
        # Base audit tasks
        base_tasks = [
            MigrationTask(
                task_id="AUDIT_001",
                title="Execute Automated Token Usage Scan",
                description="Run comprehensive token usage scanner across entire codebase",
                service="infrastructure",
                priority="critical",
                estimated_hours=2,
                dependencies=[],
                acceptance_criteria=[
                    "Token usage scanner executed successfully",
                    "Inventory report generated with all findings",
                    "Migration priorities calculated and validated"
                ]
            ),
            MigrationTask(
                task_id="AUDIT_002", 
                title="Database Schema Token Analysis",
                description="Analyze all database schemas for token column usage and dependencies",
                service="infrastructure",
                priority="high",
                estimated_hours=4,
                dependencies=["AUDIT_001"],
                acceptance_criteria=[
                    "All token columns identified and catalogued",
                    "Foreign key dependencies mapped",
                    "Index usage analysis completed",
                    "Data migration requirements documented"
                ]
            ),
            MigrationTask(
                task_id="AUDIT_003",
                title="API Endpoint Token Parameter Analysis", 
                description="Audit all API endpoints for token parameter usage",
                service="infrastructure",
                priority="high",
                estimated_hours=3,
                dependencies=["AUDIT_001"],
                acceptance_criteria=[
                    "All API endpoints accepting tokens documented",
                    "Token response patterns catalogued",
                    "Backward compatibility requirements defined"
                ]
            )
        ]
        
        # Generate service-specific audit tasks based on inventory
        if self.inventory_data:
            for service_data in self.inventory_data.get('migration_priorities', []):
                if service_data['total_findings'] > 0:
                    task = MigrationTask(
                        task_id=f"AUDIT_{service_data['service'].upper()}_001",
                        title=f"Deep Audit: {service_data['service']} Token Usage",
                        description=f"Detailed analysis of token usage in {service_data['service']} service",
                        service=service_data['service'],
                        priority=self._map_priority_from_score(service_data['migration_priority']),
                        estimated_hours=max(2, int(service_data['estimated_effort_weeks'] * 8)),
                        dependencies=["AUDIT_001"],
                        acceptance_criteria=[
                            f"All {service_data['total_findings']} token usages analyzed",
                            "Migration effort estimated for each usage",
                            "Breaking change impact assessed",
                            "Service-specific migration plan drafted"
                        ]
                    )
                    tasks.append(task)
        
        return base_tasks + tasks
    
    def _generate_contract_tasks(self) -> List[MigrationTask]:
        """Generate API contract definition tasks"""
        return [
            MigrationTask(
                task_id="CONTRACT_001",
                title="Define instrument_key Primary Contract",
                description="Establish instrument_key as mandatory primary identifier for all APIs",
                service="architecture",
                priority="critical",
                estimated_hours=4,
                dependencies=["AUDIT_002", "AUDIT_003"],
                acceptance_criteria=[
                    "API contract standards documented",
                    "instrument_key parameter requirements defined",
                    "Token derivation patterns specified",
                    "Compliance validation rules established"
                ]
            ),
            MigrationTask(
                task_id="CONTRACT_002",
                title="Implement Contract Validation Framework",
                description="Create automated validation for API contract compliance",
                service="infrastructure",
                priority="high",
                estimated_hours=6,
                dependencies=["CONTRACT_001"],
                acceptance_criteria=[
                    "Contract validation decorators implemented",
                    "Automated compliance checking tools created",
                    "Violation detection and reporting active",
                    "Integration with CI/CD pipeline complete"
                ]
            ),
            MigrationTask(
                task_id="CONTRACT_003",
                title="Design Migration Compatibility Layer",
                description="Create backward compatibility framework for gradual migration",
                service="architecture",
                priority="high",
                estimated_hours=5,
                dependencies=["CONTRACT_001"],
                acceptance_criteria=[
                    "Backward compatibility patterns defined",
                    "Legacy token acceptance framework designed",
                    "Migration timeline compatibility ensured",
                    "Deprecation warnings implemented"
                ]
            )
        ]
    
    def _generate_documentation_tasks(self) -> List[MigrationTask]:
        """Generate documentation update tasks"""
        return [
            MigrationTask(
                task_id="DOC_001",
                title="Update INSTRUMENT_DATA_ARCHITECTURE.md",
                description="Codify instrument_key primacy in data architecture documentation",
                service="documentation",
                priority="high", 
                estimated_hours=3,
                dependencies=["CONTRACT_001"],
                acceptance_criteria=[
                    "instrument_key established as primary identifier",
                    "Token usage restrictions clearly documented",
                    "Registry-first lookup patterns specified",
                    "Code examples updated with correct patterns"
                ]
            ),
            MigrationTask(
                task_id="DOC_002",
                title="Update INSTRUMENT_SUBSCRIPTION_ARCHITECTURE.md",
                description="Define key-based subscription patterns and architecture",
                service="documentation", 
                priority="high",
                estimated_hours=3,
                dependencies=["CONTRACT_001"],
                acceptance_criteria=[
                    "Key-based subscription patterns documented",
                    "Internal token resolution flows specified",
                    "Subscription state management by key defined",
                    "Multi-broker token support documented"
                ]
            ),
            MigrationTask(
                task_id="DOC_003",
                title="Create API Contract Standards Documentation",
                description="Document mandatory API standards for instrument_key usage",
                service="documentation",
                priority="medium",
                estimated_hours=4,
                dependencies=["CONTRACT_002"],
                acceptance_criteria=[
                    "API design standards documented",
                    "Compliance requirements specified",
                    "Review checklist created",
                    "Examples and anti-patterns provided"
                ]
            )
        ]
    
    def _generate_testing_tasks(self) -> List[MigrationTask]:
        """Generate testing framework tasks"""
        return [
            MigrationTask(
                task_id="TEST_001",
                title="Create Contract Compliance Test Suite",
                description="Implement automated testing for API contract compliance",
                service="testing",
                priority="high",
                estimated_hours=8,
                dependencies=["CONTRACT_002"],
                acceptance_criteria=[
                    "Contract violation tests implemented",
                    "Token derivation validation tests created",
                    "Registry lookup performance tests added",
                    "Backward compatibility tests validated"
                ]
            ),
            MigrationTask(
                task_id="TEST_002", 
                title="Performance Impact Testing Framework",
                description="Create testing for registry lookup performance impact",
                service="testing",
                priority="medium",
                estimated_hours=6,
                dependencies=["CONTRACT_001"],
                acceptance_criteria=[
                    "Registry lookup latency tests implemented",
                    "Cache effectiveness validation created",
                    "Performance baseline measurements established",
                    "SLA compliance testing automated"
                ]
            ),
            MigrationTask(
                task_id="TEST_003",
                title="Data Consistency Validation Tests",
                description="Implement testing for token-key mapping consistency",
                service="testing",
                priority="high",
                estimated_hours=5,
                dependencies=["AUDIT_002"],
                acceptance_criteria=[
                    "Token-key consistency validation implemented",
                    "Database integrity tests created",
                    "Cross-service data validation tests added",
                    "Migration data validation scripts ready"
                ]
            )
        ]
    
    def _generate_governance_tasks(self) -> List[MigrationTask]:
        """Generate governance and compliance tasks"""
        return [
            MigrationTask(
                task_id="GOV_001",
                title="Implement Code Review Compliance Checking",
                description="Add automated compliance checking to code review process",
                service="governance",
                priority="medium",
                estimated_hours=4,
                dependencies=["CONTRACT_002"],
                acceptance_criteria=[
                    "Automated compliance checker integrated",
                    "Code review checklist updated",
                    "Violation reporting implemented",
                    "Developer training materials created"
                ]
            ),
            MigrationTask(
                task_id="GOV_002",
                title="Create Deployment Gate Integration",
                description="Integrate contract compliance into deployment gates",
                service="governance", 
                priority="high",
                estimated_hours=5,
                dependencies=["TEST_001"],
                acceptance_criteria=[
                    "Deployment gate compliance checks active",
                    "Service validation automated",
                    "Compliance reporting integrated",
                    "Rollback triggers for violations implemented"
                ]
            ),
            MigrationTask(
                task_id="GOV_003",
                title="Establish Violation Monitoring",
                description="Implement real-time monitoring for contract violations",
                service="governance",
                priority="medium", 
                estimated_hours=6,
                dependencies=["CONTRACT_002"],
                acceptance_criteria=[
                    "Real-time violation detection active",
                    "Alerting for compliance breaches implemented",
                    "Violation trend analysis dashboard created",
                    "Automated reporting for compliance team"
                ]
            )
        ]
    
    def _map_priority_from_score(self, score: float) -> str:
        """Map migration priority score to task priority"""
        if score > 50:
            return "critical"
        elif score > 25:
            return "high"
        elif score > 10:
            return "medium"
        else:
            return "low"
    
    def _task_to_dict(self, task: MigrationTask) -> Dict[str, Any]:
        """Convert task to dictionary format"""
        return {
            "task_id": task.task_id,
            "title": task.title,
            "description": task.description,
            "service": task.service,
            "priority": task.priority,
            "estimated_hours": task.estimated_hours,
            "dependencies": task.dependencies,
            "acceptance_criteria": task.acceptance_criteria,
            "assignee": task.assignee,
            "status": task.status
        }
    
    def _generate_timeline(self, tasks: List[MigrationTask]) -> Dict[str, Any]:
        """Generate week-long timeline for Phase 0 tasks"""
        
        # Group tasks by priority and dependencies
        timeline = {
            "week_overview": "Phase 0: Token Usage Audit & Contract Enforcement",
            "total_estimated_hours": sum(task.estimated_hours for task in tasks),
            "daily_schedule": {}
        }
        
        # Create 5-day schedule
        start_date = datetime.now()
        for day in range(1, 6):  # Monday to Friday
            day_date = start_date + timedelta(days=day-1)
            timeline["daily_schedule"][f"day_{day}"] = {
                "date": day_date.strftime("%Y-%m-%d"),
                "focus": self._get_daily_focus(day),
                "key_tasks": self._get_daily_tasks(day, tasks),
                "deliverables": self._get_daily_deliverables(day)
            }
        
        return timeline
    
    def _get_daily_focus(self, day: int) -> str:
        """Get daily focus area"""
        focus_areas = {
            1: "Automated scanning and inventory generation",
            2: "Database and API analysis", 
            3: "Contract definition and validation framework",
            4: "Documentation updates and testing framework",
            5: "Governance implementation and validation"
        }
        return focus_areas.get(day, "Miscellaneous tasks")
    
    def _get_daily_tasks(self, day: int, tasks: List[MigrationTask]) -> List[str]:
        """Get key tasks for specific day"""
        daily_task_mapping = {
            1: ["AUDIT_001"],
            2: ["AUDIT_002", "AUDIT_003"],
            3: ["CONTRACT_001", "CONTRACT_002"],
            4: ["DOC_001", "DOC_002", "TEST_001"], 
            5: ["GOV_001", "GOV_002", "TEST_003"]
        }
        
        task_ids = daily_task_mapping.get(day, [])
        task_titles = []
        
        for task in tasks:
            if task.task_id in task_ids:
                task_titles.append(f"{task.task_id}: {task.title}")
        
        return task_titles
    
    def _get_daily_deliverables(self, day: int) -> List[str]:
        """Get expected deliverables for specific day"""
        deliverables = {
            1: [
                "Complete token usage inventory report",
                "Migration priority matrix",
                "Service-specific audit initiation"
            ],
            2: [
                "Database schema token analysis",
                "API endpoint token inventory", 
                "Data migration requirements"
            ],
            3: [
                "API contract standards defined",
                "Contract validation framework implemented",
                "Backward compatibility design"
            ],
            4: [
                "Updated architecture documentation",
                "Contract compliance test suite",
                "Performance testing framework"
            ],
            5: [
                "Governance procedures implemented",
                "Deployment gate integration",
                "Phase 0 completion validation"
            ]
        }
        return deliverables.get(day, [])
    
    def _generate_inventory_summary(self) -> Dict[str, Any]:
        """Generate summary of token usage inventory"""
        if not self.inventory_data:
            return {"status": "inventory_not_available"}
        
        return {
            "scan_timestamp": self.inventory_data.get('scan_timestamp'),
            "total_findings": self.inventory_data.get('summary_statistics', {}).get('total_findings', 0),
            "critical_issues": self.inventory_data.get('summary_statistics', {}).get('critical_issues', 0),
            "services_affected": len(self.inventory_data.get('findings_by_service', {})),
            "top_priority_services": [
                service['service'] for service in 
                self.inventory_data.get('migration_priorities', [])[:3]
            ]
        }
    
    def _define_success_criteria(self) -> List[str]:
        """Define Phase 0 success criteria"""
        return [
            "Complete token usage inventory across all services with 100% code coverage",
            "API contracts defined with instrument_key as mandatory primary identifier",
            "Contract validation framework implemented and integrated with CI/CD",
            "All architecture documentation updated with new standards",
            "Automated compliance testing suite operational",
            "Governance procedures established and enforced",
            "Migration priority plan approved with resource allocation",
            "Zero critical contract violations in new code submissions"
        ]

def generate_phase0_checklist(token_inventory_file: str, output_file: str = None) -> str:
    """Generate comprehensive Phase 0 execution checklist"""
    
    generator = Phase0ChecklistGenerator(token_inventory_file)
    checklist = generator.generate_complete_checklist()
    
    # Generate output filename if not provided
    if not output_file:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f'phase0_execution_checklist_{timestamp}.json'
    
    # Write checklist to file
    with open(output_file, 'w') as f:
        json.dump(checklist, f, indent=2)
    
    # Generate summary display
    summary = f"""
📋 PHASE 0 EXECUTION CHECKLIST GENERATED
{'='*60}

⏱️  TIMELINE: {checklist['duration']}
📊 TOTAL TASKS: {len(checklist['all_tasks'])}
⚡ ESTIMATED EFFORT: {sum(task['estimated_hours'] for task in checklist['all_tasks'])} hours

🎯 INVENTORY SUMMARY:
"""
    
    inventory = checklist['inventory_summary']
    if 'total_findings' in inventory:
        summary += f"   • Total token findings: {inventory['total_findings']}\n"
        summary += f"   • Critical issues: {inventory['critical_issues']}\n"
        summary += f"   • Services affected: {inventory['services_affected']}\n"
        summary += f"   • Top priority services: {', '.join(inventory['top_priority_services'])}\n"
    else:
        summary += "   • Inventory data will be generated during execution\n"
    
    summary += f"""
📅 DAILY SCHEDULE:
"""
    
    for day_key, day_info in checklist['timeline']['daily_schedule'].items():
        day_num = day_key.split('_')[1]
        summary += f"   Day {day_num} ({day_info['date']}): {day_info['focus']}\n"
        for task in day_info['key_tasks'][:2]:  # Show first 2 tasks
            summary += f"      • {task}\n"
    
    summary += f"""
✅ SUCCESS CRITERIA:
"""
    for criterion in checklist['success_criteria'][:3]:  # Show first 3 criteria
        summary += f"   • {criterion}\n"
    
    summary += f"   • [and {len(checklist['success_criteria'])-3} more criteria...]\n"
    
    summary += f"""
📁 Detailed checklist saved to: {output_file}
"""
    
    print(summary)
    return output_file

# CLI interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate Phase 0 execution checklist')
    parser.add_argument('--inventory', '-i', required=True,
                       help='Token usage inventory JSON file')
    parser.add_argument('--output', '-o',
                       help='Output file for checklist (JSON)')
    
    args = parser.parse_args()
    
    print("📋 Generating Phase 0 execution checklist...")
    output_file = generate_phase0_checklist(args.inventory, args.output)
    print(f"✅ Phase 0 checklist generated: {output_file}")