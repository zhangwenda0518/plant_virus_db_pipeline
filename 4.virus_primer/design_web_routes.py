#!/usr/bin/env python3
"""
Design web routes — pluggable into the Flask app in step5_web_server.py.
Import and call register_design_routes(app) to add all design endpoints.
"""

import io
from datetime import datetime
from urllib.parse import unquote

from Bio import SeqIO
from flask import request, jsonify, render_template_string, redirect

from primer_design_service import DesignJobManager


def _build_results_html(results):
    """Build an HTML table from design results list (kept for potential server-side use)."""
    if not results:
        return '<div class="alert alert-warning">暂无结果</div>'

    lines = [
        '<div class="table-responsive"><table class="table table-hover table-sm">',
        '<thead class="table-dark"><tr><th>#</th><th>正向引物 (5\'→3\')</th>',
        '<th>反向引物 (5\'→3\')</th><th>产物</th><th>Tm(F/R)</th>',
        '<th>GC%(F/R)</th><th>方法</th><th>评分</th></tr></thead><tbody>'
    ]
    for i, r in enumerate(results):
        fwd = r.get('Fwd_Seq', '')
        rev = r.get('Rev_Seq', '')
        prod = r.get('Product', '')
        tm_f = round(float(r.get('Fwd_Tm', 0)), 1)
        tm_r = round(float(r.get('Rev_Tm', 0)), 1)
        gc_f = round(float(r.get('GC_Fwd', 0)), 1)
        gc_r = round(float(r.get('GC_Rev', 0)), 1)
        method = r.get('Method', '')
        penalty = r.get('Penalty', '')
        probe = r.get('Probe_Seq', '')
        fwd_start = r.get('Fwd_Start', 0)
        rev_start = r.get('Rev_Start', 0)

        lines.append(
            '<tr>'
            '<td>{}</td>'
            '<td><span class="primer-seq">{}</span></td>'
            '<td><span class="primer-seq">{}</span></td>'
            '<td>{}bp</td><td>{}/{}&deg;C</td>'
            '<td>{}/{}%</td><td>{}</td>'
            '<td>{}</td>'
            '</tr>'.format(
                i + 1, fwd, rev, prod, tm_f, tm_r,
                gc_f, gc_r, method, penalty
            )
        )
        if probe:
            lines.append(
                '<tr><td></td><td colspan="7">'
                '<span class="probe-seq">探针: {}</span></td></tr>'.format(probe)
            )
    lines.append('</tbody></table></div>')
    return ''.join(lines)


def register_design_routes(app):
    """Register all design-related routes on the Flask app."""

    # ── Design page ──
    @app.route('/design')
    def design_page():
        mgr = app.config.get('design_mgr')
        jobs = mgr.list_jobs(limit=20) if mgr else []
        return render_template_string(
            app.config.get('DESIGN_TEMPLATE', 'Design template not loaded'),
            jobs=jobs, year=datetime.now().year
        )

    # ── Design results page (redirects to design page for inline display) ──
    @app.route('/design/results/<job_id>')
    def design_results(job_id):
        # Redirect to the design page with job_id as query param.
        # The design page JS auto-loads results inline when ?job_id= is present.
        return redirect('/primers/design?job_id={}'.format(job_id))

    # ── API: upload FASTA ──
    @app.route('/api/design/upload', methods=['POST'])
    def api_design_upload():
        mgr = app.config.get('design_mgr')
        if not mgr:
            return jsonify({"error": "Design service not available"}), 503

        if 'fasta' not in request.files:
            return jsonify({"error": "No FASTA file provided"}), 400

        fasta_file = request.files['fasta']
        if fasta_file.filename == '':
            return jsonify({"error": "Empty filename"}), 400

        try:
            content_bytes = fasta_file.read()
            content_text = content_bytes.decode('utf-8', errors='replace')
        except Exception as e:
            return jsonify({"error": "Failed to read file: {}".format(e)}), 400

        sequences = []
        try:
            for record in SeqIO.parse(io.StringIO(content_text), "fasta"):
                sequences.append(str(record.seq).upper().replace('U', 'T'))
        except Exception as e:
            return jsonify({"error": "Invalid FASTA format: {}".format(e)}), 400

        if not sequences:
            return jsonify({"error": "No sequences found in FASTA file"}), 400

        species_name = request.form.get('species_name', '').strip()
        if not species_name:
            try:
                first = next(SeqIO.parse(io.StringIO(content_text), "fasta"))
                species_name = first.description.split('[')[0].strip()[:50] or first.id[:50]
            except Exception:
                species_name = "custom_input"

        mode = request.form.get('mode', 'PCR').strip()
        num_pairs = int(request.form.get('num_pairs', 5))
        prod_min = int(request.form.get('prod_min', 250))
        prod_max = int(request.form.get('prod_max', 1000))

        try:
            job_id = mgr.submit(
                sequences=sequences,
                species_name=species_name,
                design_mode=mode,
                num_pairs=num_pairs,
                prod_min=prod_min,
                prod_max=prod_max
            )
            return jsonify({"job_id": job_id, "status": "submitted"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── API: design for known species ──
    @app.route('/api/design/species/<path:species>', methods=['POST'])
    def api_design_species(species):
        species = unquote(species)
        mgr = app.config.get('design_mgr')
        if not mgr:
            return jsonify({"error": "Design service not available"}), 503

        data = request.get_json(silent=True) or {}
        mode = data.get('mode', 'PCR').strip()
        num_pairs = int(data.get('num_pairs', 5))
        prod_min = int(data.get('prod_min', 250))
        prod_max = int(data.get('prod_max', 1000))

        try:
            job_id = mgr.submit(
                species_name=species,
                design_mode=mode,
                num_pairs=num_pairs,
                prod_min=prod_min,
                prod_max=prod_max
            )
            return jsonify({"job_id": job_id, "status": "submitted"})
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── API: job status ──
    @app.route('/api/design/status/<job_id>')
    def api_design_status(job_id):
        mgr = app.config.get('design_mgr')
        if not mgr:
            return jsonify({"error": "Design service not available"}), 503
        status = mgr.status(job_id)
        if not status:
            return jsonify({"error": "Job not found"}), 404
        return jsonify(status)

    # ── API: get results ──
    @app.route('/api/design/results/<job_id>')
    def api_design_results(job_id):
        mgr = app.config.get('design_mgr')
        if not mgr:
            return jsonify({"error": "Design service not available"}), 503

        fmt = request.args.get('format', 'json')
        status = mgr.status(job_id)
        if not status:
            return jsonify({"error": "Job not found"}), 404
        if status['status'] != 'completed':
            return jsonify({"error": "Job not completed", "status": status['status']}), 400

        if fmt == 'tsv':
            tsv = mgr.results_tsv(job_id)
            return tsv, 200, {'Content-Type': 'text/plain; charset=utf-8'}

        results = mgr.results(job_id)
        if fmt == 'fasta':
            lines = []
            sp = status.get('species_name', 'unknown')
            mode = status.get('design_mode', '')
            for i, r in enumerate(results or []):
                lines.append(">{}|{}|{}|FWD".format(sp, mode, i + 1))
                lines.append(r.get('Fwd_Seq', ''))
                lines.append(">{}|{}|{}|REV".format(sp, mode, i + 1))
                lines.append(r.get('Rev_Seq', ''))
            return '\n'.join(lines), 200, {'Content-Type': 'text/plain; charset=utf-8'}

        return jsonify(results or [])

    # ── API: list known species ──
    @app.route('/api/design/species-list')
    def api_design_species_list():
        mgr = app.config.get('design_mgr')
        if not mgr:
            return jsonify({"species": [], "error": "Design service not available"})
        query = request.args.get('q', '').strip()
        species = mgr.list_known_species(query=query, limit=100)
        return jsonify({"species": species, "count": len(species)})
