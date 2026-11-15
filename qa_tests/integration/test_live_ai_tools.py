"""Real local-model application preparation and Copilot persistence in isolated Neon."""
import io

from reportlab.pdfgen import canvas


def test_real_cover_letter_tailoring_and_copilot_history(clients):
    first, second = clients
    document = io.BytesIO()
    pdf = canvas.Canvas(document)
    for index, text in enumerate([
        'Synthetic Engineer - Software Engineer',
        'SKILLS: Python, FastAPI, PostgreSQL, SQL, Git',
        'EXPERIENCE: Built a Python API with request validation and automated tests.',
        'PROJECTS: Created PostgreSQL-backed services and documented REST endpoints.',
    ]):
        pdf.drawString(40, 780 - index * 25, text)
    pdf.save()
    uploaded = first.post('/resume/upload', files={'file': ('ai-tools-check.pdf', document.getvalue(), 'application/pdf')})
    assert uploaded.status_code == 200, uploaded.text
    letter = first.post('/resume/cover-letter', json={'target_role': 'Software Engineer', 'company_name': 'Synthetic Test Company', 'tone': 'formal'})
    assert letter.status_code == 200, letter.text
    assert len(letter.json()['cover_letter'].strip()) > 80
    assert 'Python' in letter.json()['cover_letter']
    tailored = first.post('/resume/tailor', json={'job_description': 'Software Engineer building Python and FastAPI services with PostgreSQL and automated API tests.'})
    assert tailored.status_code == 200, tailored.text
    result = tailored.json()
    assert result['tailored_resume'].strip()
    assert isinstance(result['keyword_changes'], list)
    assert 0 <= result['ats_score_estimate'] <= 100
    created = first.post('/copilot/sessions')
    assert created.status_code == 201
    chat = first.post('/copilot/chat', json={'session_id': created.json()['session_id'], 'message': 'Which programming language is explicitly listed in my resume? Answer in one short sentence.', 'stream': False})
    assert chat.status_code == 200, chat.text
    assert 'python' in chat.json()['response'].lower()
    session_id = chat.json()['session_id']
    history = first.get('/copilot/history/' + session_id)
    assert history.status_code == 200 and len(history.json()) >= 2
    peer_history = second.get('/copilot/history/' + session_id)
    assert peer_history.status_code == 200 and peer_history.json() == []
