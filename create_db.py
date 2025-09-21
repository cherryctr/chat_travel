#!/usr/bin/env python3
"""
Script untuk membuat database dan tabel SQLite
Jalankan script ini untuk setup database development
"""

import os
import sys
from pathlib import Path

# Add the app directory to Python path
sys.path.append(str(Path(__file__).parent))

from app.db.session import engine, Base
from app.db.models import User, Trip, Booking

def create_database():
    """Membuat database dan semua tabel"""
    print("🚀 Membuat database SQLite...")
    
    try:
        # Create all tables
        Base.metadata.create_all(bind=engine)
        print("✅ Database dan tabel berhasil dibuat!")
        print(f"📁 Database file: {os.path.abspath('chat_gemini.db')}")
        
        # Test connection
        from sqlalchemy.orm import sessionmaker
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()
        
        # Test query
        user_count = db.query(User).count()
        trip_count = db.query(Trip).count()
        booking_count = db.query(Booking).count()
        
        print(f"📊 Data awal:")
        print(f"   - Users: {user_count}")
        print(f"   - Trips: {trip_count}")
        print(f"   - Bookings: {booking_count}")
        
        db.close()
        print("✅ Koneksi database berhasil!")
        
    except Exception as e:
        print(f"❌ Error membuat database: {e}")
        return False
    
    return True

if __name__ == "__main__":
    create_database()
