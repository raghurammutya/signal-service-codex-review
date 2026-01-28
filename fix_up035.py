#!/usr/bin/env python3
"""
Quick script to fix UP035 deprecated typing imports
"""
import re
from pathlib import Path

# Mapping of deprecated imports to modern equivalents
DEPRECATED_IMPORTS = {
    'dict': 'dict',
    'list': 'list',
    'tuple': 'tuple',
    'set': 'set',
    'frozenset': 'frozenset',
    'DefaultDict': 'collections.defaultdict',
    'Counter': 'collections.Counter',
    'Deque': 'collections.deque',
    'OrderedDict': 'collections.OrderedDict',
    'ChainMap': 'collections.ChainMap',
    'AsyncContextManager': 'contextlib.AbstractAsyncContextManager',
    'ContextManager': 'contextlib.AbstractContextManager',
    'AsyncGenerator': 'collections.abc.AsyncGenerator',
    'AsyncIterable': 'collections.abc.AsyncIterable',
    'AsyncIterator': 'collections.abc.AsyncIterator',
    'Awaitable': 'collections.abc.Awaitable',
    'Callable': 'collections.abc.Callable',
    'Collection': 'collections.abc.Collection',
    'Container': 'collections.abc.Container',
    'Coroutine': 'collections.abc.Coroutine',
    'Generator': 'collections.abc.Generator',
    'Hashable': 'collections.abc.Hashable',
    'Iterable': 'collections.abc.Iterable',
    'Iterator': 'collections.abc.Iterator',
    'KeysView': 'collections.abc.KeysView',
    'Mapping': 'collections.abc.Mapping',
    'MappingView': 'collections.abc.MappingView',
    'MutableMapping': 'collections.abc.MutableMapping',
    'MutableSequence': 'collections.abc.MutableSequence',
    'MutableSet': 'collections.abc.MutableSet',
    'Sequence': 'collections.abc.Sequence',
    'Sized': 'collections.abc.Sized',
    'ValuesView': 'collections.abc.ValuesView',
    'ItemsView': 'collections.abc.ItemsView'
}

def fix_file(file_path: Path) -> bool:
    """Fix UP035 violations in a single file"""
    try:
        with open(file_path) as f:
            content = f.read()

        original_content = content

        # Find typing import lines
        import_lines = []
        for line_no, line in enumerate(content.split('\n')):
            if re.match(r'^\s*from\s+typing\s+import', line):
                import_lines.append((line_no, line))

        # Process each import line
        for _line_no, line in import_lines:
            # Extract imports from the line
            match = re.match(r'^(\s*from\s+typing\s+import\s+)(.+)$', line)
            if not match:
                continue

            prefix = match.group(1)
            imports_str = match.group(2)

            # Parse the imports (handle multi-line and complex cases)
            imports = []
            current_import = ""
            paren_depth = 0

            for char in imports_str:
                if char == '(':
                    paren_depth += 1
                elif char == ')':
                    paren_depth -= 1

                if char == ',' and paren_depth == 0:
                    imports.append(current_import.strip())
                    current_import = ""
                else:
                    current_import += char

            if current_import.strip():
                imports.append(current_import.strip())

            # Filter out deprecated imports
            new_imports = []
            for imp in imports:
                imp = imp.strip()
                if imp in DEPRECATED_IMPORTS:
                    # Skip deprecated imports
                    continue
                new_imports.append(imp)

            # Rebuild the import line
            if new_imports:
                new_line = prefix + ', '.join(new_imports)
                content = content.replace(line, new_line)
            else:
                # Remove the entire import line
                content = content.replace(line + '\n', '')
                content = content.replace(line, '')

        # Replace usage of deprecated types with modern equivalents
        for deprecated, modern in DEPRECATED_IMPORTS.items():
            if modern in ['dict', 'list', 'tuple', 'set', 'frozenset']:
                # Simple built-in types
                content = re.sub(r'\b' + deprecated + r'\b', modern, content)

        if content != original_content:
            with open(file_path, 'w') as f:
                f.write(content)
            return True

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False

    return False

def main():
    """Fix all UP035 violations in the project"""
    project_root = Path(__file__).parent

    # Find all Python files
    python_files = []
    for pattern in ['**/*.py']:
        python_files.extend(project_root.glob(pattern))

    fixed_count = 0
    for file_path in python_files:
        if 'signal_service_legacy' in str(file_path):
            continue

        if fix_file(file_path):
            print(f"Fixed: {file_path}")
            fixed_count += 1

    print(f"\nFixed {fixed_count} files")

if __name__ == '__main__':
    main()
