from flask import Flask, request, jsonify, render_template, session
from openai import OpenAI
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# System prompt for detailed responses ✅
SYSTEM_PROMPT = (
    "You are GROK, a helpful assistant. Respond briefly and directly:\n"
    "\n"
    "For SIMPLE questions (name, greeting, basic info from our conversation):\n"
    "- Give a short, direct answer (1 sentence maximum)\n"
    "- Don't ask follow-up questions or elaborate\n"
    "- Just answer what was asked\n"
    "\n"
    "For SERVICE PROVIDER questions (best service, who provides, recommendations):\n"
    "- Start directly with specific recommendations\n"
    "- Give 2-3 concrete options with names, locations, and contact info\n"
    "- Include a short 'How to verify' section with 3-4 bullet points\n"
    "- Total response should be 150-300 words maximum\n"
    "\n"
"For GENERAL questions:\n"
    "- Give clear, concise answers\n"
    "- Don't over-explain or ask follow-ups unless requested\n"
    "\n"
    "ALWAYS:\n"
    "- Be direct and to-the-point\n"
    "- Don't ask unnecessary follow-up questions\n"
    "- No markdown formatting\n"
    "- Answer the question asked, nothing more"
)


load_dotenv()
app = Flask(__name__)
app.secret_key = os.urandom(24)

# GROK client exactly as per X.AI documentation
client = OpenAI(
    api_key=os.getenv("GROK_API_KEY"),
    base_url="https://api.x.ai/v1"
)

# Session timeout configuration (prevents long-running sessions)
@app.before_request
def make_session_permanent():
    session.permanent = True
    app.permanent_session_lifetime = timedelta(minutes=30)  # 30 min timeout ✅
    session.modified = True

# Usage tracking for compliance
def track_usage(prompt_tokens, completion_tokens):
    """Track API usage to prevent excessive consumption"""
    if 'usage_today' not in session:
        session['usage_today'] = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'requests': 0,
            'prompt_tokens': 0,
            'completion_tokens': 0
        }
    
    # Reset daily usage
    if session['usage_today']['date'] != datetime.now().strftime('%Y-%m-%d'):
        session['usage_today'] = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'requests': 0,
            'prompt_tokens': 0,
            'completion_tokens': 0
        }
    
    session['usage_today']['requests'] += 1
    session['usage_today']['prompt_tokens'] += prompt_tokens
    session['usage_today']['completion_tokens'] += completion_tokens

def check_rate_limit():
    """Prevent excessive API usage as per guidelines"""
    usage = session.get('usage_today', {})
    
    # Reasonable daily limits to prevent excessive consumption
    if usage.get('requests', 0) > 50:  # Max 50 requests per day per user
        return False, "Daily request limit reached (50). Please try again tomorrow."
    
    if usage.get('completion_tokens', 0) > 25000:  # Max 25k tokens per day
        return False, "Daily token limit reached. Please try again tomorrow."
    
    return True, None

@app.route('/')
def home():
    # Initialize session conversation
    if 'conversation' not in session:
        session['conversation'] = []
        session['session_start'] = datetime.now().isoformat()
    
    return render_template('index.html')

@app.route('/query', methods=['POST'])
def query_route():
    # Check session timeout
    if 'conversation' not in session:
        return jsonify({'error': 'Session expired. Please refresh the page.'}), 440
    
    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 400
    
    data = request.get_json()
    if not data or 'query' not in data:
        return jsonify({'error': 'Missing "query" parameter'}), 400
    
    # Rate limiting check (compliance requirement)
    can_proceed, error_msg = check_rate_limit()
    if not can_proceed:
        return jsonify({'error': error_msg}), 429
    
    try:
        # Build conversation with system prompt and history
        conversation_messages = (
            [{"role": "system", "content": SYSTEM_PROMPT}]
            + [
                m
                for c in session.get("conversation", [])[-3:]  # last 3 exchanges
                for m in (
                    {"role": "user", "content": c["user"]},
                    {"role": "assistant", "content": c["grok"]},
                )
            ]
            + [{"role": "user", "content": f"Please provide a comprehensive, detailed answer: {data['query']}"}]
        )
        
        # EXACTLY as per X.AI documentation
        completion = client.chat.completions.create(
            model="grok-4",  #grok model
            messages=conversation_messages,
            temperature=0.8,  # Higher for more creative detailed responses
            max_tokens=1200   # Increased for longer detailed answers
        )
        
        # Track usage for compliance monitoring ✅
        usage = completion.usage
        track_usage(usage.prompt_tokens, usage.completion_tokens)
        
        # Get and clean response ✅
        content = completion.choices[0].message.content
        if content:
            content = content.replace('**', '').replace('*', '')  # Remove markdown
        
        # Handle empty responses
        if not content or not content.strip():
            content = (
                "I couldn't generate a detailed response. Let me try a different approach. "
                "Could you rephrase your question or provide more specific details about what you're looking for?"
            )
        
        # ✅ FIXED: Store in session conversation (with timeout)
        conversation = session.get('conversation', [])
        conversation.append({
            'user': data['query'],
            'grok': content,  # Use cleaned content
            'timestamp': datetime.now().isoformat()
        })
        
        # Keep only last 10 exchanges to prevent memory bloat
        session['conversation'] = conversation[-10:]
        
        # ✅ FIXED: Return cleaned content
        return jsonify({
            "status": "success",
            "query": data['query'],
            "response": content,  # Use cleaned content instead of raw completion
            "model": "grok-4",
            "usage": {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens
            },
            "session_active": True
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/session-status')
def session_status():
    """Check session status (helps with timeout handling)"""
    return jsonify({
        'active': 'conversation' in session,
        'conversation_count': len(session.get('conversation', [])),
        'session_start': session.get('session_start', 'unknown'),
        'usage_today': session.get('usage_today', {})
    })

@app.route('/clear-session', methods=['POST'])
def clear_session():
    """Manual session cleanup"""
    session.clear()
    return jsonify({'status': 'cleared'})

@app.route('/favicon.ico')
def favicon():
    """Handle favicon requests to avoid 404 errors"""
    return '', 204

if __name__ == '__main__':
    print("🚀 GROK Chatbot - Enhanced Version")
    print("📋 Features:")
    print("   ✅ 30-minute session timeout")
    print("   ✅ Daily usage limits")
    print("   ✅ Model: grok-2-1212")
    print("   ✅ Detailed system prompts")
    print("   ✅ Conversation memory")
    print("   ✅ Markdown cleaning")
    print("   ✅ Enhanced responses")
    print("   ✅ No background/automated calls")
    print("   ✅ Usage monitoring")
    print("🌐 Open browser to: http://localhost:5000")
    
    app.run(debug=True, port=5000)
