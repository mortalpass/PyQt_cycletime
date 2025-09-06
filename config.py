import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
LOG_BASE = os.path.join(PROJECT_ROOT, 'data', 'input')
OUTPUT_BASE = os.path.join(PROJECT_ROOT, 'data', 'output')

output_log = os.path.join(OUTPUT_BASE, 'sort_logs')

output_form = os.path.join(OUTPUT_BASE, 'form')

output_img = os.path.join(OUTPUT_BASE, 'img')

index_path = os.path.join(PROJECT_ROOT, 'src', 'package', 'important_index.txt')
