"""
Email Service Layer - Handles all email communication for AI Powered Assistance Platform
Supports SMTP (Gmail) with HTML templates
"""

import smtplib
import logging
from typing import List, Optional, Dict, Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import httpx
from jinja2 import Environment, select_autoescape
from app.config import settings

logger = logging.getLogger(__name__)

# Autoescaping Jinja2 environment for all HTML email rendering (M2)
jinja_env = Environment(
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


class EmailService:
    """Service to handle all email communications"""
    _last_sent_verification_link: Optional[str] = None
    _last_sent_reset_link: Optional[str] = None
    _last_sent_verification_token: Optional[str] = None
    _last_sent_password_reset_token: Optional[str] = None
    
    @staticmethod
    def send_email(
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> bool:
        """
        Send an email using SMTP
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML email body
            text_content: Plain text fallback
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = settings.EMAIL_FROM
            msg["To"] = to_email
            
            # Attach plain text and HTML parts
            if text_content:
                msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))
            
            # Connect to SMTP server and send
            if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
                raise ValueError("SMTP credentials are not configured")

            if settings.EMAIL_FROM != settings.SMTP_USERNAME:
                logger.warning("EMAIL_FROM differs from SMTP_USERNAME. Some SMTP providers may reject the message.")

            smtp_timeout = getattr(settings, "SMTP_TIMEOUT", 10.0)
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=smtp_timeout) as server:
                server.starttls()
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)
            
            logger.info(f"✅ Email sent to {to_email}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send email to {to_email}: {str(e)}")
            if settings.RESEND_API_KEY:
                logger.info("ℹ️ Falling back to Resend email delivery")
                return EmailService.send_email_via_resend(to_email, subject, html_content, text_content)
            return False

    @staticmethod
    def send_verification_email(email: str, full_name: str, verification_link: str) -> bool:
        """Send email verification link"""
        import urllib.parse
        EmailService._last_sent_verification_link = verification_link
        parsed = urllib.parse.urlparse(verification_link)
        params = urllib.parse.parse_qs(parsed.query)
        tok = params.get("token", [None])[0]
        if tok:
            EmailService._last_sent_verification_token = tok
        
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; background-color: #f4f4f4; }
                .container { max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; }
                .header { background-color: #4f46e5; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }
                .content { padding: 20px; }
                .button { background-color: #4f46e5; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 20px 0; }
                .footer { background-color: #f9fafb; padding: 10px; text-align: center; font-size: 12px; color: #6b7280; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Welcome to AI Powered Assistance Platform 🚀</h1>
                </div>
                <div class="content">
                    <p>Hi {{ full_name }},</p>
                    <p>Thank you for registering with AI Powered Assistance Platform! To get started, please verify your email address by clicking the link below:</p>
                    <a href="{{ verification_link }}" class="button">Verify Your Email</a>
                    <p>Or copy and paste this link in your browser:</p>
                    <p><code>{{ verification_link }}</code></p>
                    <p>This link expires in 24 hours.</p>
                    <p>If you didn't create this account, please ignore this email.</p>
                </div>
                <div class="footer">
                    <p>&copy; 2026 AI Powered Assistance Platform. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        template = jinja_env.from_string(html_template)
        html_content = template.render(full_name=full_name, verification_link=verification_link)
        
        text_content = f"""
        Welcome to AI Powered Assistance Platform!
        
        Hi {full_name},
        
        Please verify your email by visiting: {verification_link}
        This link expires in 24 hours.
        """
        
        success = EmailService.send_email(
            to_email=email,
            subject="Verify Your AI Powered Assistance Platform Email Address",
            html_content=html_content,
            text_content=text_content
        )
        if not success:
            logger.warning(f"\n==================================================\n[DEVELOPMENT ONLY] Verification Link for {email}:\n{verification_link}\n==================================================\n")
        return success

    @staticmethod
    def send_password_reset(
        to_email: str,
        reset_token: str,
        frontend_url: Optional[str] = None
    ) -> bool:
        """Send password reset using the same contract as app.utils.email_service."""
        EmailService._last_sent_password_reset_token = reset_token
        if frontend_url is None:
            frontend_url = settings.FRONTEND_URL
        reset_link = f"{frontend_url}/reset-password?token={reset_token}"
        EmailService._last_sent_reset_link = reset_link
        return EmailService.send_password_reset_email(
            email=to_email,
            full_name="User",
            reset_link=reset_link
        )

    @staticmethod
    def send_email_via_resend(
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> bool:
        """Send an email using the Resend API as a fallback."""
        if not settings.RESEND_API_KEY:
            logger.error("❌ RESEND_API_KEY is not configured. Cannot send email via Resend.")
            return False

        try:
            payload = {
                "from": settings.EMAIL_FROM,
                "to": [to_email],
                "subject": subject,
                "html": html_content,
                "text": text_content or ""
            }
            headers = {
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type": "application/json"
            }
            response = httpx.post("https://api.resend.com/emails", json=payload, headers=headers, timeout=10)
            if response.status_code in {200, 201}:
                logger.info(f"✅ Email sent via Resend to {to_email}: {subject}")
                return True
            logger.error(
                f"❌ Resend API failed with status {response.status_code}: {response.text}"
            )
            return False
        except Exception as e:
            logger.error(f"❌ Failed to send email via Resend to {to_email}: {str(e)}")
            return False

    @staticmethod
    def send_password_reset_email(email: str, full_name: str, reset_link: str) -> bool:
        """Send password reset link"""
        import urllib.parse
        EmailService._last_sent_reset_link = reset_link
        parsed = urllib.parse.urlparse(reset_link)
        params = urllib.parse.parse_qs(parsed.query)
        tok = params.get("token", [None])[0]
        if tok:
            EmailService._last_sent_password_reset_token = tok
        
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; background-color: #f4f4f4; }
                .container { max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; }
                .header { background-color: #ef4444; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }
                .content { padding: 20px; }
                .button { background-color: #ef4444; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 20px 0; }
                .footer { background-color: #f9fafb; padding: 10px; text-align: center; font-size: 12px; color: #6b7280; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Password Reset Request</h1>
                </div>
                <div class="content">
                    <p>Hi {{ full_name }},</p>
                    <p>We received a request to reset your password. Click the link below to create a new password:</p>
                    <a href="{{ reset_link }}" class="button">Reset Your Password</a>
                    <p>Or copy and paste this link in your browser:</p>
                    <p><code>{{ reset_link }}</code></p>
                    <p>This link expires in 15 minutes.</p>
                    <p>If you didn't request a password reset, please ignore this email or contact support.</p>
                </div>
                <div class="footer">
                    <p>&copy; 2026 AI Powered Assistance Platform. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        template = jinja_env.from_string(html_template)
        html_content = template.render(full_name=full_name, reset_link=reset_link)
        
        text_content = f"""
        Password Reset Request
        
        Hi {full_name},
        
        Please reset your password by visiting: {reset_link}
        This link expires in 15 minutes.
        """
        
        success = EmailService.send_email(
            to_email=email,
            subject="Reset Your AI Powered Assistance Platform Password",
            html_content=html_content,
            text_content=text_content
        )
        if not success:
            logger.warning(f"\n==================================================\n[DEVELOPMENT ONLY] Password Reset Link for {email}:\n{reset_link}\n==================================================\n")
        return success

    @staticmethod
    def send_job_application_email(email: str, full_name: str, job_title: str, 
                                   company: str, application_date: str) -> bool:
        """Send job application confirmation email"""
        
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; background-color: #f4f4f4; }
                .container { max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; }
                .header { background-color: #10b981; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }
                .content { padding: 20px; }
                .job-details { background-color: #f0fdf4; padding: 15px; border-left: 4px solid #10b981; margin: 15px 0; }
                .footer { background-color: #f9fafb; padding: 10px; text-align: center; font-size: 12px; color: #6b7280; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Application Submitted Successfully! ✓</h1>
                </div>
                <div class="content">
                    <p>Hi {{ full_name }},</p>
                    <p>We've recorded your job application. Here are the details:</p>
                    <div class="job-details">
                        <p><strong>Job Title:</strong> {{ job_title }}</p>
                        <p><strong>Company:</strong> {{ company }}</p>
                        <p><strong>Application Date:</strong> {{ application_date }}</p>
                        <p><strong>Status:</strong> Pending Review</p>
                    </div>
                    <p>We'll track this application and notify you of any updates. Keep applying to increase your chances!</p>
                    <p>Good luck! 🍀</p>
                </div>
                <div class="footer">
                    <p>&copy; 2026 AI Powered Assistance Platform. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        template = jinja_env.from_string(html_template)
        html_content = template.render(
            full_name=full_name,
            job_title=job_title,
            company=company,
            application_date=application_date
        )
        
        text_content = f"""
        Application Submitted Successfully!
        
        Hi {full_name},
        
        Job Title: {job_title}
        Company: {company}
        Date: {application_date}
        
        We'll notify you of any updates!
        """
        
        return EmailService.send_email(
            to_email=email,
            subject=f"Application Submitted for {job_title} at {company}",
            html_content=html_content,
            text_content=text_content
        )

    @staticmethod
    def send_job_alert_email(email: str, full_name: str, jobs: List[Dict[str, Any]]) -> bool:
        """Send daily job alert email with matching jobs"""
        
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; background-color: #f4f4f4; }
                .container { max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; }
                .header { background-color: #3b82f6; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }
                .content { padding: 20px; }
                .job-item { background-color: #f0f9ff; padding: 15px; margin: 10px 0; border-left: 4px solid #3b82f6; border-radius: 4px; }
                .job-item h3 { margin-top: 0; }
                .button { background-color: #3b82f6; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 10px 0; }
                .footer { background-color: #f9fafb; padding: 10px; text-align: center; font-size: 12px; color: #6b7280; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎯 Daily Job Alerts</h1>
                </div>
                <div class="content">
                    <p>Hi {{ full_name }},</p>
                    <p>We found {{ job_count }} new job(s) matching your profile today:</p>
                    {% for job in jobs %}
                    <div class="job-item">
                        <h3>{{ job.get('title', 'N/A') }}</h3>
                        <p><strong>Company:</strong> {{ job.get('company', 'N/A') }}</p>
                        <p><strong>Location:</strong> {{ job.get('location', 'Remote') }}</p>
                        <p><strong>Match Score:</strong> {{ job.get('match_score', 0) }}%</p>
                    </div>
                    {% endfor %}
                    <a href="{{ dashboard_link }}" class="button">View All Jobs in Dashboard</a>
                </div>
                <div class="footer">
                    <p>&copy; 2026 AI Powered Assistance Platform. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        template = jinja_env.from_string(html_template)
        html_content = template.render(
            full_name=full_name,
            job_count=len(jobs),
            jobs=jobs[:10],
            dashboard_link=settings.FRONTEND_URL + "/job-board"
        )
        
        return EmailService.send_email(
            to_email=email,
            subject=f"🎯 Your Daily Job Alerts - {len(jobs)} New Opportunities",
            html_content=html_content
        )

    @staticmethod
    def send_weekly_summary_email(email: str, full_name: str, 
                                 total_applications: int, 
                                 applications: List[Dict[str, Any]]) -> bool:
        """Send weekly application summary email"""
        
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; background-color: #f4f4f4; }
                .container { max-width: 700px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; }
                .header { background-color: #8b5cf6; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }
                .content { padding: 20px; }
                .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 20px 0; }
                .stat-box { background-color: #f3e8ff; padding: 15px; border-radius: 8px; text-align: center; }
                .stat-number { font-size: 24px; font-weight: bold; color: #8b5cf6; }
                table { width: 100%; border-collapse: collapse; margin: 20px 0; }
                th, td { padding: 10px; text-align: left; border-bottom: 1px solid #e5e7eb; }
                th { background-color: #f9fafb; font-weight: bold; }
                .footer { background-color: #f9fafb; padding: 10px; text-align: center; font-size: 12px; color: #6b7280; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 Weekly Job Application Summary</h1>
                </div>
                <div class="content">
                    <p>Hi {{ full_name }},</p>
                    <p>Here's your weekly job search summary:</p>
                    
                    <div class="stats">
                        <div class="stat-box">
                            <p>Applications This Week</p>
                            <p class="stat-number">{{ total_applications }}</p>
                        </div>
                        <div class="stat-box">
                            <p>Companies Targeted</p>
                            <p class="stat-number">{{ unique_companies }}</p>
                        </div>
                    </div>
                    
                    <h3>Recent Applications:</h3>
                    <table>
                        <tr>
                            <th>Job Title</th>
                            <th>Company</th>
                            <th>Status</th>
                            <th>Date</th>
                        </tr>
                        {% for app in applications %}
                        <tr>
                            <td>{{ app.get('title', 'N/A') }}</td>
                            <td>{{ app.get('company', 'N/A') }}</td>
                            <td>{{ app.get('status', 'pending')|capitalize }}</td>
                            <td>{{ app.get('applied_date', 'N/A') }}</td>
                        </tr>
                        {% endfor %}
                    </table>
                    
                    <p>Keep up the great momentum! Consistency is key to landing your dream job. 🚀</p>
                </div>
                <div class="footer">
                    <p>&copy; 2026 AI Powered Assistance Platform. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        unique_companies = len(set(app.get('company', '') for app in applications))
        
        template = jinja_env.from_string(html_template)
        html_content = template.render(
            full_name=full_name,
            total_applications=total_applications,
            unique_companies=unique_companies,
            applications=applications[:20]
        )
        
        text_content = f"""
        Weekly Job Application Summary
        
        Hi {full_name},
        
        Applications This Week: {total_applications}
        Unique Companies: {unique_companies}
        
        Keep applying! Consistency is key. 🚀
        """
        
        return EmailService.send_email(
            to_email=email,
            subject=f"📊 Your Weekly Summary - {total_applications} Applications",
            html_content=html_content,
            text_content=text_content
        )

    @staticmethod
    def send_feedback_email(user_email: str, user_name: str, feedback_text: str) -> bool:
        """Send feedback email to administrator and backup locally"""
        import json
        from pathlib import Path
        from datetime import datetime

        logger.info(f"\n[FEEDBACK RECEIVED] From: {user_name} ({user_email})")
        logger.info(f"Content: {feedback_text}\n")

        # Save to local backups
        try:
            feedback_dir = Path("./data")
            feedback_dir.mkdir(exist_ok=True)
            feedback_file = feedback_dir / "feedbacks.json"
            
            feedbacks = []
            if feedback_file.exists():
                try:
                    with open(feedback_file, "r") as f:
                        feedbacks = json.load(f)
                except Exception:
                    pass
            
            feedbacks.append({
                "timestamp": datetime.utcnow().isoformat(),
                "user_name": user_name,
                "user_email": user_email,
                "feedback": feedback_text
            })
            
            with open(feedback_file, "w") as f:
                json.dump(feedbacks, f, indent=4)
            logger.info("[FEEDBACK] Successfully persisted feedback locally.")
        except Exception as e:
            logger.error(f"[FEEDBACK] Failed to write local backup: {e}")

        # Send to admin email
        subject = f"New AI Powered Assistance Platform Feedback from {user_name}"
        html_template = """
        <h2>New Feedback Received</h2>
        <p><strong>From:</strong> {{ user_name }} ({{ user_email }})</p>
        <p><strong>Message:</strong></p>
        <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0; white-space: pre-wrap;">
            {{ feedback_text }}
        </div>
        """
        template = jinja_env.from_string(html_template)
        html_content = template.render(
            user_name=user_name,
            user_email=user_email,
            feedback_text=feedback_text
        )
        text_content = f"New Feedback Received\n\nFrom: {user_name} ({user_email})\n\nMessage:\n{feedback_text}"
        
        # Try sending (automatically uses SMTP and/or falls back to Resend)
        return EmailService.send_email(
            to_email="reddymurali144@gmail.com",
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    @staticmethod
    def send_job_match_alert(to_email: str, job_title: str, company: str, match_score: float) -> bool:
        """Send job match notification email"""
        subject = f"🎯 {match_score:.0f}% Match: {job_title} at {company}"
        html_template = """
        <h2>You Have a New Job Match!</h2>
        <p>We found a job that matches your profile:</p>
        
        <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
            <h3>{{ job_title }}</h3>
            <p><strong>{{ company }}</strong></p>
            <p><strong>Match Score: {{ match_score }}%</strong></p>
        </div>
        
        <p><a href="{{ frontend_url }}/jobs/matched" 
            style="background-color: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
            View Job
        </a></p>
        
        <p>Check AI Powered Assistance Platform to see tailored cover letter and resume bullets for this role.</p>
        """
        template = jinja_env.from_string(html_template)
        html_content = template.render(
            job_title=job_title,
            company=company,
            match_score=f"{match_score:.1f}",
            frontend_url=settings.FRONTEND_URL
        )
        text_content = f"You Have a New Job Match!\n\n{job_title} at {company} (Match Score: {match_score:.1f}%)"
        return EmailService.send_email(to_email, subject, html_content, text_content)

    @staticmethod
    def send_application_reminder(to_email: str, company: str, job_title: str) -> bool:
        """Send application reminder email"""
        subject = f"📋 Ready to Apply: {job_title} at {company}"
        html_template = """
        <h2>Your Application Package is Ready</h2>
        <p>AI Powered Assistance Platform has generated a tailored cover letter and resume for:</p>
        
        <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
            <h3>{{ job_title }}</h3>
            <p><strong>{{ company }}</strong></p>
        </div>
        
        <p><a href="{{ frontend_url }}/apply" 
            style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
            View Application Package
        </a></p>
        
        <p>Click the link above to review your tailored materials before submitting.</p>
        """
        template = jinja_env.from_string(html_template)
        html_content = template.render(
            job_title=job_title,
            company=company,
            frontend_url=settings.FRONTEND_URL
        )
        text_content = f"Your Application Package is Ready: {job_title} at {company}"
        return EmailService.send_email(to_email, subject, html_content, text_content)

