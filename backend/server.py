import os
from flask import Flask, send_from_directory, jsonify
from .component_registry import ComponentRegistry

app = Flask(__name__)

# Path for the public directory
PUBLIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'public'))

# Path for the components directory
COMPONENTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'components'))

# Path for the frontend directory
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))

@app.route('/api/components')
def get_components():
    if not os.path.isdir(COMPONENTS_DIR):
        app.logger.error(f"Components directory not found at {COMPONENTS_DIR}")
        return jsonify(error="Components directory not found"), 500

    registry = ComponentRegistry()
    try:
        registry.discover_components(COMPONENTS_DIR)
    except Exception as e:
        app.logger.error(f"Error discovering components: {e}")
        return jsonify(error=f"Error discovering components: {str(e)}"), 500

    return jsonify(list(registry.manifests.values()))

@app.route('/frontend/<path:filename>')
def serve_frontend_files(filename):
    return send_from_directory(FRONTEND_DIR, filename)

@app.route('/')
def serve_index():
    return send_from_directory(PUBLIC_DIR, 'index.html')

@app.errorhandler(404)
def page_not_found(e):
    return jsonify(error=str(e)), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
