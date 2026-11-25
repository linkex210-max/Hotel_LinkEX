from datetime import date, timedelta
from decimal import Decimal
from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.db.models import Q, F
from apps.bookings.models import Booking, BookingStatusHistory
from apps.properties.models import Property, RoomType, Unit, RoomTypeInventory, SeasonalPricing

class BookingService:
    @staticmethod
    def get_date_range(start_date: date, end_date: date):
        """قائمة بجميع التواريخ في نطاق الإقامة (ليلة بليلة باستثناء يوم المغادرة)"""
        current = start_date
        while current < end_date:
            yield current
            current += timedelta(days=1)

    @classmethod
    def is_room_type_available(cls, room_type: RoomType, check_in: date, check_out: date, rooms_count: int = 1) -> bool:
        """
        فحص التوفر فائق السرعة O(1) عبر جدول المخزون اليومي RoomTypeInventory
        إذا لم تكن التواريخ مسجلة بالمخزون بعد، يتم الحساب التلقائي من إجمالي غرف الفئة
        """
        if check_in >= check_out:
            raise ValidationError("تاريخ المغادرة يجب أن يكون بعد تاريخ الوصول")

        total_capacity = room_type.total_inventory_units
        if total_capacity < rooms_count:
            return False

        dates = list(cls.get_date_range(check_in, check_out))

        # جلب سجلات المخزون اليومي لهذه الفترة
        inventory_records = {
            inv.date: inv
            for inv in RoomTypeInventory.objects.filter(
                room_type=room_type,
                date__in=dates
            )
        }

        for single_date in dates:
            inv = inventory_records.get(single_date)
            if inv:
                if inv.is_closed or inv.available_rooms < rooms_count:
                    return False
            else:
                # في حال عدم إنشاء سجل مخزون لهذا التاريخ، نفحص الحجوزات النشطة
                active_bookings_count = Booking.objects.filter(
                    room_type=room_type,
                    status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.CHECKED_IN],
                    check_in_date__lt=single_date + timedelta(days=1),
                    check_out_date__gt=single_date
                ).count()
                if (total_capacity - active_bookings_count) < rooms_count:
                    return False

        return True

    @classmethod
    def calculate_nightly_breakdown(cls, room_type: RoomType, check_in: date, check_out: date) -> dict:
        """
        احتساب تفصيل أسعار كل ليلة بدقة (Audit Trail & Dynamic Pricing)
        لضمان العدالة في استرجاع الأموال واحتساب الضرائب
        """
        if check_in >= check_out:
            raise ValidationError("تاريخ المغادرة يجب أن يكون بعد تاريخ الوصول")

        dates = list(cls.get_date_range(check_in, check_out))
        nights = len(dates)

        breakdown = []
        subtotal = Decimal("0.00")

        # جلب الأسعار الموسمية مع تقديم القواعد المحددة لنوع الغرفة على القواعد العامة للعقار
        seasonal_rules = list(SeasonalPricing.objects.filter(
            Q(room_type=room_type) | Q(property=room_type.property, room_type__isnull=True),
            is_active=True,
            start_date__lte=check_out,
            end_date__gte=check_in
        ).order_by(models.F('room_type_id').desc(nulls_last=True), '-id'))

        # جلب أسعار المخزون المخصصة
        daily_prices = {
            inv.date: inv.price
            for inv in RoomTypeInventory.objects.filter(room_type=room_type, date__in=dates)
        }

        for single_date in dates:
            # 1. الأولوية لسعر اليوم في جدول المخزون إن وجد
            if single_date in daily_prices:
                night_rate = daily_prices[single_date]
            else:
                night_rate = room_type.base_price

                # 2. فحص الأسعار الموسمية المنطبقة على هذا اليوم
                for rule in seasonal_rules:
                    if rule.start_date <= single_date <= rule.end_date:
                        if rule.fixed_price:
                            night_rate = rule.fixed_price
                        else:
                            night_rate = (night_rate * rule.price_multiplier).quantize(Decimal("0.01"))
                        break

            subtotal += night_rate
            breakdown.append({
                "date": single_date.isoformat(),
                "rate": f"{night_rate.quantize(Decimal('0.01')):.2f}",
            })

        from apps.finance.models import TaxRate
        tax_rate_pct = TaxRate.get_rate_for_date(check_in)
        avg_base_rate = (subtotal / Decimal(nights)).quantize(Decimal("0.01"))
        tax_amount = (subtotal * (tax_rate_pct / Decimal("100.00"))).quantize(Decimal("0.01"))
        total_amount = subtotal + tax_amount

        return {
            "nights": nights,
            "nights_breakdown": breakdown,
            "avg_base_rate": avg_base_rate,
            "subtotal": subtotal,
            "tax_rate": tax_rate_pct,
            "tax_amount": tax_amount,
            "discount_amount": Decimal("0.00"),
            "total_amount": total_amount
        }

    @classmethod
    def create_booking_atomic(cls, booking_data: dict, user=None) -> Booking:
        """
        إنشاء حجز ذري مع قفل فئة الغرفة وتحديث جدول المخزون اليومي
        لمنع الـ Double-Booking تماماً
        """
        with transaction.atomic():
            room_type = RoomType.objects.select_for_update().get(id=booking_data["room_type_id"])
            if not room_type.is_active or not room_type.property.is_active:
                raise ValueError("Room type or property is inactive")

            check_in = booking_data["check_in_date"]
            check_out = booking_data["check_out_date"]

            if not cls.is_room_type_available(room_type, check_in, check_out):
                raise ValueError(f"عفواً، لا يتوفر عدد كافٍ من غرف '{room_type.name}' في الفترة المحددة")

            calc = cls.calculate_nightly_breakdown(room_type, check_in, check_out)

            # في حال تم تمرير وحدة محددة (مثل الشاليهات)
            unit = None
            if booking_data.get("unit_id"):
                unit = Unit.objects.select_for_update().get(id=booking_data["unit_id"])
                if (not unit.is_active or unit.property_id != room_type.property_id
                        or unit.room_type_id != room_type.id):
                    raise ValueError("Unit does not belong to the selected room type and property")
                overlaps = Booking.objects.filter(
                    unit=unit,
                    status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.CHECKED_IN],
                    check_in_date__lt=check_out,
                    check_out_date__gt=check_in,
                ).exists()
                if overlaps:
                    raise ValueError("Unit is already booked for these dates")

            booking = Booking.objects.create(
                property=room_type.property,
                room_type=room_type,
                unit=unit,
                guest=user if (user and user.is_authenticated) else None,
                guest_name=booking_data["guest_name"],
                guest_phone=booking_data["guest_phone"],
                guest_national_id=booking_data.get("guest_national_id", ""),
                check_in_date=check_in,
                check_out_date=check_out,
                status=Booking.Status.PENDING,
                source=booking_data.get("source", Booking.BookingSource.ONLINE),
                total_nights=calc["nights"],
                nights_breakdown=calc["nights_breakdown"],
                base_rate=calc["avg_base_rate"],
                subtotal=calc["subtotal"],
                tax_rate=calc["tax_rate"],
                tax_amount=calc["tax_amount"],
                discount_amount=calc["discount_amount"],
                total_amount=calc["total_amount"],
                special_requests=booking_data.get("special_requests", "")
            )

            # تحديث عدد المحجوز في جدول المخزون اليومي لكل ليلة
            for night in calc["nights_breakdown"]:
                d = date.fromisoformat(night["date"])
                inv, _ = RoomTypeInventory.objects.get_or_create(
                    room_type=room_type,
                    date=d,
                    defaults={
                        "total_rooms": room_type.total_inventory_units,
                        "booked_rooms": 0,
                        "price": Decimal(str(night["rate"]))
                    }
                )
                inv.booked_rooms += 1
                inv.save()

            BookingStatusHistory.objects.create(
                booking=booking,
                from_status="NONE",
                to_status=Booking.Status.PENDING,
                changed_by=user if (user and user.is_authenticated) else None,
                notes="حجز جديد بنجاح"
            )

            return booking

    @staticmethod
    def assign_room_unit(booking: Booking, unit: Unit, user=None):
        """تسكين النزيل وتعيين رقم الغرفة الفعلي عند الدخول مع ضمان Lock Ordering ومنع Race Conditions"""
        with transaction.atomic():
            # 1. القفل المتسق أولاً للحجز لمنع الـ Deadlock مع transition_status
            booking = Booking.objects.select_for_update().get(pk=booking.pk)
            if booking.status not in [Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.CHECKED_IN]:
                raise ValidationError("لا يمكن تعيين غرفة لحجز ملغي أو منتهي")

            # 2. قفل الوحدة الفعلية بعد الحجز
            unit = Unit.objects.select_for_update().get(pk=unit.pk)

            # 3. التحقق الدقيق بعد الحصول على الأقفال
            if unit.property_id != booking.property_id or unit.room_type_id != booking.room_type_id:
                raise ValidationError("الغرفة لا تنتمي لنفس الفندق أو فئة الغرفة")
            if unit.status != Unit.Status.AVAILABLE and booking.unit_id != unit.id:
                raise ValidationError(f"الغرفة رقم {unit.unit_number} غير متاحة حالياً ({unit.get_status_display()})")

            overlaps = Booking.objects.filter(
                unit=unit,
                status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.CHECKED_IN],
                check_in_date__lt=booking.check_out_date,
                check_out_date__gt=booking.check_in_date,
            ).exclude(pk=booking.pk).exists()
            if overlaps:
                raise ValidationError("Unit is already assigned to an overlapping booking")

            booking.unit = unit
            booking.save(update_fields=["unit", "updated_at"])

    @staticmethod
    def transition_status(booking: Booking, new_status: str, user=None, notes: str = ""):
        allowed = {
            Booking.Status.PENDING: {Booking.Status.CONFIRMED, Booking.Status.CANCELLED, Booking.Status.NO_SHOW},
            Booking.Status.CONFIRMED: {Booking.Status.CHECKED_IN, Booking.Status.CANCELLED, Booking.Status.NO_SHOW},
            Booking.Status.CHECKED_IN: {Booking.Status.CHECKED_OUT},
        }
        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(pk=booking.pk)
            old_status = booking.status
            if new_status not in allowed.get(old_status, set()):
                raise ValidationError("Invalid booking status transition")
            booking.status = new_status
            booking.save(update_fields=["status", "updated_at"])

            if new_status in (Booking.Status.CANCELLED, Booking.Status.NO_SHOW):
                for night in booking.nights_breakdown:
                    day = date.fromisoformat(night["date"])
                    inventory = RoomTypeInventory.objects.select_for_update().filter(
                        room_type=booking.room_type, date=day
                    ).first()
                    if inventory and inventory.booked_rooms > 0:
                        inventory.booked_rooms -= 1
                        inventory.save(update_fields=["booked_rooms"])

            if booking.unit_id:
                unit = Unit.objects.select_for_update().get(pk=booking.unit_id)
                if new_status == Booking.Status.CHECKED_IN:
                    unit.status = Unit.Status.OCCUPIED
                    unit.save(update_fields=["status"])
                elif new_status == Booking.Status.CHECKED_OUT:
                    unit.status = Unit.Status.CLEANING
                    unit.save(update_fields=["status"])
                elif new_status in (Booking.Status.CANCELLED, Booking.Status.NO_SHOW):
                    unit.status = Unit.Status.AVAILABLE
                    unit.save(update_fields=["status"])

            BookingStatusHistory.objects.create(
                booking=booking,
                from_status=old_status,
                to_status=new_status,
                changed_by=user if (user and user.is_authenticated) else None,
                notes=notes,
            )
