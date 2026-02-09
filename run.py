#!/usr/bin/env python3
"""
Simple script to run the QBank Generator app on port 5001
"""
from app import app

if __name__ == '__main__':
    app.run(debug=True, port=5001, host='127.0.0.1')
