import os
import datetime
from app.models import db, mail
from sqlalchemy.exc import SQLAlchemyError
# import model class
from app.models.order import Order
from app.models.order_details import OrderDetails
from app.models.user import User
from app.models.payment import Payment
from app.models.order_verification import OrderVerification
from app.models.ticket import Ticket
from app.models.base_model import BaseModel
from app.models.booth import Booth
from app.models.user_booth import UserBooth
from app.models.hacker_team import HackerTeam
from app.models.user_hacker import UserHacker
from app.models.redeem_code import RedeemCode
from app.services.base_service import BaseService
from app.services.email_service import EmailService
from app.builders.response_builder import ResponseBuilder
from app.services.user_ticket_service import UserTicketService
from app.services.redeem_code_service import RedeemCodeService
from app.services.fcm_service import FCMService
from flask import current_app
from PIL import Image
from app.configs.constants import IMAGE_QUALITY, ROLE
from app.services.helper import Helper
from app.configs.constants import TICKET_TYPES
from app.configs.settings import LOCAL_TIME_ZONE
from werkzeug import secure_filename


class OrderVerificationService(BaseService):
	
	def get(self):
		orderverifications = db.session.query(OrderVerification).filter_by(is_used=0).all()
		_result = []
		for entry in orderverifications:
			data = entry.as_dict()
			data = self.transformTimeZone(data)
			if data['payment_proof']:
				data['payment_proof'] = Helper().url_helper(data['payment_proof'], current_app.config['GET_DEST'])
			else:
				data['payment_proof'] = ""
			data['user'] = entry.user.include_photos().as_dict()
			_result.append(data)
		
		return _result

	def create(self, payload):
		response = ResponseBuilder()
		orderverification_query = db.session.query(OrderVerification).filter_by(order_id=payload['order_id'])
		orderverification = orderverification_query.first()
		payment_proof = self.save_file(payload['payment_proof']) if payload['payment_proof'] is not None else None
		if orderverification:
			if orderverification.payment_proof is not None:
				Helper().silent_remove(current_app.config['STATIC_DEST'] + orderverification.payment_proof)
			orderverification_query.update({
				'payment_proof': payment_proof,
				'updated_at': datetime.datetime.now()
			})
		else:
			orderverification = OrderVerification()
			order = db.session.query(Order).filter_by(id=payload['order_id']).first()
			orderverification.user_id = order.user_id
			orderverification.order_id = payload['order_id']
			orderverification.payment_proof = payment_proof
			db.session.add(orderverification)
		try:
			db.session.commit()
			result = orderverification.as_dict()
			result['payment_proof'] = Helper().url_helper(result['payment_proof'], current_app.config['GET_DEST'])
			return response.set_data(result).set_message('Data created succesfully').build()
		except SQLAlchemyError as e:
			data = e.orig.args
			return response.set_data(data).set_error(True).build()

	def show(self, id):
		response = ResponseBuilder()
		orderverification = db.session.query(OrderVerification).filter_by(order_id=id).first()
		data = orderverification.as_dict() if orderverification else None
		if data:
			if data['payment_proof']:
				data['payment_proof'] = Helper().url_helper(data['payment_proof'], current_app.config['GET_DEST'])
			else:
				data['payment_proof'] = ""
			return response.set_data(data).build()
		return response.set_error(True).set_message('data not found').set_data(None).build()


	def update(self, id, payload):
		response = ResponseBuilder()
		orderverification = db.session.query(OrderVerification).filter_by(id=id)
		data = orderverification.first().as_dict() if orderverification.first() else None
		if data['payment_proof'] is not None and payload['payment_proof']:
			Helper().silent_remove(current_app.config['STATIC_DEST'] + data['payment_proof'])
		if data is None:
			return response.set_error(True).set_message('data not found').set_data(None).build()
		payment_proof = self.save_file(payload['payment_proof']) if payload['payment_proof'] is not None else None
		try:
			orderverification = db.session.query(OrderVerification).filter_by(id=id)			
			orderverification.update({
				'user_id': payload['user_id'],
				'order_id': payload['order_id'],
				'payment_proof': payment_proof,
				'updated_at': datetime.datetime.now()
			})
			db.session.commit()
			data = orderverification.first()
			return response.set_data(data.as_dict()).build()
		except SQLAlchemyError as e:
			data = e.orig.args
			return response.set_error(True).set_data(data).build()

	def delete(self, id):
		response = ResponseBuilder()
		orderverification = db.session.query(OrderVerification).filter_by(id=id).first()
		if orderverification.payment_proof is not None:
			Helper().silent_remove(current_app.config['STATIC_DEST'] + orderverification.payment_proof)
		orderverification = db.session.query(OrderVerification).filter_by(id=id)
		if orderverification.first() is not None:
			orderverification.delete()
			db.session.commit()
			return response.set_message('Order Verification entry was deleted').build()
		else:
			data = 'Entry not found'
			return response.set_data(None).set_message(data).set_error(True).build()

	def save_file(self, file, id=None):
		image = Image.open(file, 'r')
		if file and Helper().allowed_file(file.filename, current_app.config['ALLOWED_EXTENSIONS']):
			if (Helper().allowed_file(file.filename, ['jpg', 'jpeg', 'png'])):
				image = image.convert("RGB")
			filename = secure_filename(file.filename)
			filename = Helper().time_string() + "_" + file.filename.replace(" ", "_")
			image.save(os.path.join(current_app.config['POST_PAYMENT_PROOF_DEST'], filename), quality=IMAGE_QUALITY, optimize=True)
			return current_app.config['SAVE_PAYMENT_PROOF_DEST'] + filename
		else:
			return None

	def create_booth(self, user):
		booth = Booth()
		booth.name = 'Your booth name here'
		booth.user_id = user.id
		booth.points = 0
		booth.summary = ''
		booth.logo_url = None
		booth.stage_id = None
		db.session.add(booth)
		db.session.commit()
		userbooth = UserBooth()
		userbooth.user_id = user.id
		userbooth.booth_id = booth.id
		db.session.add(userbooth)
		db.session.commit()

	def create_hackaton (self, user, ticket_id):
		hacker_team = HackerTeam()
		hacker_team.name = 'Your team name here'
		hacker_team.logo = None
		hacker_team.project_name = 'Your project name here'
		hacker_team.project_url = 'Project name'
		hacker_team.theme = 'Project link'
		hacker_team.ticket_id = ticket_id
		db.session.add(hacker_team)
		db.session.commit()
		userhacker = UserHacker()
		userhacker.user_id = user.id
		userhacker.hacker_team_id = hacker_team.id
		db.session.add(userhacker)
		db.session.commit()
		return hacker_team.id

	def verify(self, id):
		response = ResponseBuilder()
		emailservice = EmailService()		
		orderverification_query = db.session.query(OrderVerification).filter_by(id=id)
		orderverification = orderverification_query.first()
		if orderverification.is_used is not 1:
			user_query = db.session.query(User).filter_by(id=orderverification.user_id)
			user = user_query.first()
			items = db.session.query(OrderDetails).filter_by(order_id=orderverification.order_id).all()
			if items[0].ticket.type == TICKET_TYPES['exhibitor']:
				payload = {}
				payload['user_id'] = user.id
				payload['ticket_id'] = items[0].ticket_id
				UserTicketService().create(payload)
				self.create_booth(user)
				user_query.update({
					'role_id': ROLE['booth']
				})
				redeem_payload = {}
				redeem_payload['ticket_id'] = items[0].ticket_id
				redeem_payload['codeable_id'] = user.id
				RedeemCodeService().purchase_user_redeems(redeem_payload)
				get_codes = db.session.query(RedeemCode).filter_by(codeable_type='user', codeable_id=user.id).all()
				code = []
				for get_code in get_codes:
					code.append("<li>%s</li>" %(get_code.code))
				li = ''.join(code)
				template = "<h3>You have complete the payment with order_id = %s</h3><h4>Here are the redeem codes for claiming full 3 days ticket at devsummit event as described in the package information : </h4>%s<h3>Use the above code to claim your ticket</h3><h3>Thank you for your purchase</h3>" %(orderverification.order_id, li)
				email = emailservice.set_recipient(user.email).set_subject('Congratulations !! you received exhibitor code').set_sender('noreply@devsummit.io').set_html(template).build()
				mail.send(email)
			elif items[0].ticket.type == TICKET_TYPES['hackaton']:
				payload = {}
				payload['user_id'] = user.id
				payload['ticket_id'] = items[0].ticket_id
				UserTicketService().create(payload)
				hackerteam_id = self.create_hackaton(user, items[0].ticket_id)
				user_query.update({
					'role_id': ROLE['hackaton']
				})
				redeem_payload = {}
				redeem_payload['codeable_type'] = TICKET_TYPES['hackaton']
				redeem_payload['codeable_id'] = hackerteam_id
				redeem_payload['count'] = items[0].ticket.quota
				RedeemCodeService().create(redeem_payload)
				get_codes = db.session.query(RedeemCode).filter_by(codeable_type='hackaton', codeable_id=hackerteam_id).all()
				code = []
				for get_code in get_codes:
					code.append("<li>%s</li>" %(get_code.code))
				li = ''.join(code)
				template = "<h3>You have complete the payment with order_id = %s</h3><h4>Here your redeem codes : </h4>%s<h3>Share the above code to your teammate, and put it into redeem code menu to let them join your team and claim their ticket</h3><h3>Thank you for your purchase</h3>" %(orderverification.order_id, li)
				email = emailservice.set_recipient(user.email).set_subject('Congratulations !! you received hackaton code').set_sender('noreply@devsummit.io').set_html(template).build()
				mail.send(email)
			else:
				for item in items:
					for i in range(0, item.count):
						payload = {}
						payload['user_id'] = user.id
						payload['ticket_id'] = item.ticket_id
						UserTicketService().create(payload)
			orderverification_query.update({
				'is_used': 1
			})
			payment_query = db.session.query(Payment).filter_by(order_id=orderverification.order_id)
			payment_query.update({
				'transaction_status': 'captured'
			})
			completed_order = db.session.query(Order).filter_by(id=orderverification.order_id)
			completed_order.update({
				'status': 'paid'
			})
			db.session.commit()
			send_notification = FCMService().send_single_notification('Payment Status', 'Your payment has been verified', user.id, ROLE['admin'])
			return response.set_data(None).set_message('ticket purchased').build()
		else:
			return response.set_data(None).set_message('This payment has already verified').build()

	def transformTimeZone(self, obj):
		entry = obj
		created_at_timezoned = datetime.datetime.strptime(entry['created_at'], "%Y-%m-%d %H:%M:%S") + datetime.timedelta(hours=LOCAL_TIME_ZONE)
		entry['created_at'] = str(created_at_timezoned).rsplit('.', maxsplit=1)[0] + " WIB"
		updated_at_timezoned = datetime.datetime.strptime(entry['updated_at'], "%Y-%m-%d %H:%M:%S") + datetime.timedelta(hours=LOCAL_TIME_ZONE)
		entry['updated_at'] = str(updated_at_timezoned).rsplit('.', maxsplit=1)[0] + " WIB"
		return entry
