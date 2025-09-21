from sqlalchemy import Column, BigInteger, Integer, String, Date, DateTime, ForeignKey, Enum, DECIMAL, Text
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.db.session import Base


class User(Base):
	__tablename__ = "users"

	id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
	name: Mapped[str] = mapped_column(String(255), nullable=False)
	email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
	email_verified_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
	password: Mapped[str] = mapped_column(String(255), nullable=False)
	remember_token: Mapped[str | None] = mapped_column(String(100), nullable=True)
	created_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
	updated_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)

	bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="user")


class Trip(Base):
	__tablename__ = "trips"

	id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
	name: Mapped[str] = mapped_column(String(255), nullable=False)
	slug: Mapped[str] = mapped_column(String(255), nullable=False)
	location: Mapped[str] = mapped_column(String(255), nullable=False)
	duration: Mapped[str] = mapped_column(String(255), nullable=False)
	price: Mapped[float] = mapped_column(DECIMAL(12, 2), nullable=False)
	status: Mapped[str] = mapped_column(Enum("draft", "published", "archived"), nullable=False)
	is_active: Mapped[int] = mapped_column(Integer, nullable=False)


class Booking(Base):
	__tablename__ = "bookings"

	id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
	booking_code: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
	trip_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("trips.id"), nullable=False)
	trip_schedule_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
	promo_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
	customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
	customer_email: Mapped[str] = mapped_column(String(255), ForeignKey("users.email"), nullable=False)
	customer_phone: Mapped[str] = mapped_column(String(255), nullable=False)
	customer_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
	emergency_contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
	emergency_contact_phone: Mapped[str | None] = mapped_column(String(255), nullable=True)
	trip_type: Mapped[str] = mapped_column(Enum("public", "private"), nullable=False)
	departure_date: Mapped[Date] = mapped_column(Date, nullable=False)
	participants: Mapped[int] = mapped_column(Integer, nullable=False)
	total_amount: Mapped[float] = mapped_column(DECIMAL(12, 2), nullable=False)
	status: Mapped[str] = mapped_column(Enum("pending", "confirmed", "paid", "cancelled", "completed"), nullable=False)
	payment_status: Mapped[str] = mapped_column(Enum("pending", "partial", "paid", "refunded"), nullable=False)
	created_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
	updated_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)

	trip: Mapped[Trip] = relationship("Trip")
	user: Mapped[User | None] = relationship("User", back_populates="bookings")
