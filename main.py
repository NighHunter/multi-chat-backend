# main.py

from typing import Generator, List, Optional
from datetime import datetime
import json
import os
from uuid import uuid4

from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    UploadFile,
    File,
    Form,
    Query,  # <--- already there
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from database import SessionLocal, engine, Base
from models import User, Class, ClassMember, Message
from sqlalchemy import text


# ----------------------------------------------------
# App + CORS
# ----------------------------------------------------
app = FastAPI(title="Class Multi-Chat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for local dev; tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------
# DB setup
# ----------------------------------------------------
Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ----------------------------------------------------
# Uploads folder + static mount
# ----------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# NEW: separate folder for avatar images
AVATAR_DIR = os.path.join(UPLOAD_DIR, "avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)

# Serve uploaded files under /uploads/...
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# ====================================================
# Pydantic Schemas
# ====================================================

# ---- Student auth ----
class StudentRegister(BaseModel):
    full_name: str
    student_id: str
    email: EmailStr
    password: str


class StudentLoginRequest(BaseModel):
    student_id: str
    password: str


class StudentLoginResponse(BaseModel):
    token: str
    role: str
    full_name: str
    email: EmailStr
    student_id: str


# ---- Admin auth ----
class AdminRegister(BaseModel):
    full_name: str
    email: EmailStr
    password: str


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str


class AdminLoginResponse(BaseModel):
    token: str
    role: str
    full_name: str
    email: EmailStr


# ---- Teacher (lecturer) auth & admin creation ----
class TeacherCreate(BaseModel):
    full_name: str
    email: EmailStr
    staff_id: str
    temp_password: str


class TeacherOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    staff_id: str
    password: Optional[str] = None  # exposed to admin UI

    class Config:
        orm_mode = True


class TeacherLoginRequest(BaseModel):
    staff_id: str
    password: str


class TeacherLoginResponse(BaseModel):
    token: str
    role: str
    full_name: str
    email: EmailStr
    staff_id: str


# ---- Student list for admin ----
class StudentOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    student_id: str
    password: Optional[str] = None  # exposed to admin UI

    class Config:
        orm_mode = True


# ---- User profile (for avatar etc.) ----
class UserProfile(BaseModel):
    full_name: str
    email: EmailStr
    role: str
    student_id: Optional[str] = None
    staff_id: Optional[str] = None
    avatar_url: Optional[str] = None

    class Config:
        orm_mode = True


# ---- Classes & membership ----
class CreateClassRequest(BaseModel):
    name: str
    semester: Optional[str] = None
    description: Optional[str] = None
    code: str
    owner_email: EmailStr


class ClassOut(BaseModel):
    id: int
    name: str
    semester: Optional[str]
    description: Optional[str]
    code: str

    class Config:
        orm_mode = True


class JoinClassRequest(BaseModel):
    student_email: EmailStr
    code: str


class ApproveRequest(BaseModel):
    class_id: int
    student_email: EmailStr


class MemberOut(BaseModel):
    email: EmailStr
    role: str
    status: str

    class Config:
        orm_mode = True


class RemoveClassRequest(BaseModel):
    class_id: int
    owner_email: EmailStr


# ---- Messages & attachments ----
class AttachmentMeta(BaseModel):
    filename: str
    url: str
    content_type: str


class MessageCreate(BaseModel):
    channel: str
    sender_email: EmailStr
    sender_name: str
    content: str
    attachments: List[AttachmentMeta] = []


class MessageOut(BaseModel):
    id: int
    class_id: int
    channel: str
    sender_email: EmailStr
    sender_name: str
    content: str
    timestamp: datetime
    attachments: List[AttachmentMeta] = []

    class Config:
        orm_mode = True


class DeleteMessageRequest(BaseModel):
    own_email: EmailStr


# ====================================================
# Health
# ====================================================
@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Class Multi-Chat backend is running"}


# ====================================================
# Student auth
# ====================================================
@app.post("/auth/register/student")
def register_student(data: StudentRegister, db: Session = Depends(get_db)):
    sid = data.student_id.strip().lower()
    email = data.email.strip().lower()

    existing_by_sid = db.query(User).filter(User.student_id == sid).first()
    if existing_by_sid:
        raise HTTPException(status_code=400, detail="Student ID already registered")

    existing_by_email = db.query(User).filter(User.email == email).first()
    if existing_by_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        full_name=data.full_name.strip(),
        email=email,
        password=data.password,  # TODO: hash
        role="student",
        student_id=sid,
        staff_id=None,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "message": "Student registered",
        "student": {
            "full_name": user.full_name,
            "student_id": user.student_id,
            "email": user.email,
            "role": user.role,
        },
    }


@app.post("/auth/login/student", response_model=StudentLoginResponse)
def login_student(data: StudentLoginRequest, db: Session = Depends(get_db)):
    sid = data.student_id.strip().lower()

    user = (
        db.query(User)
        .filter(
            User.student_id == sid,
            User.role == "student",
        )
        .first()
    )

    if not user or user.password != data.password:
        raise HTTPException(status_code=401, detail="Invalid user ID or password")

    return StudentLoginResponse(
        token="demo-token",
        role=user.role,
        full_name=user.full_name,
        email=user.email,
        student_id=user.student_id or "",
    )


# ====================================================
# Admin auth
# ====================================================
@app.post("/auth/register/admin", response_model=AdminLoginResponse)
def register_admin(data: AdminRegister, db: Session = Depends(get_db)):
    existing_admin = db.query(User).filter(User.role == "admin").first()
    if existing_admin:
        raise HTTPException(status_code=400, detail="Admin already exists")

    email = data.email.strip().lower()

    existing_by_email = db.query(User).filter(User.email == email).first()
    if existing_by_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        full_name=data.full_name.strip(),
        email=email,
        password=data.password,
        role="admin",
        student_id=None,
        staff_id=None,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return AdminLoginResponse(
        token="demo-token",
        role=user.role,
        full_name=user.full_name,
        email=user.email,
    )


@app.post("/auth/login/admin", response_model=AdminLoginResponse)
def login_admin(data: AdminLoginRequest, db: Session = Depends(get_db)):
    email = data.email.strip().lower()

    user = (
        db.query(User)
        .filter(
            User.email == email,
            User.role == "admin",
        )
        .first()
    )

    if not user or user.password != data.password:
        raise HTTPException(status_code=401, detail="Invalid user ID or password")

    return AdminLoginResponse(
        token="demo-token",
        role=user.role,
        full_name=user.full_name,
        email=user.email,
    )


# ====================================================
# Admin: manage teachers & students
# ====================================================
@app.post("/admin/teachers", response_model=TeacherOut)
def create_teacher(data: TeacherCreate, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    staff_id = data.staff_id.strip()

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    if db.query(User).filter(User.staff_id == staff_id).first():
        raise HTTPException(status_code=400, detail="Staff ID already registered")

    user = User(
        full_name=data.full_name.strip(),
        email=email,
        password=data.temp_password,  # temp password
        role="teacher",
        student_id=None,
        staff_id=staff_id,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@app.get("/admin/teachers", response_model=List[TeacherOut])
def list_teachers(db: Session = Depends(get_db)):
    teachers = (
        db.query(User)
        .filter(User.role == "teacher")
        .order_by(User.full_name)
        .all()
    )
    return teachers


@app.delete("/admin/teachers/{teacher_id}")
def delete_teacher(teacher_id: int, db: Session = Depends(get_db)):
    teacher = (
        db.query(User)
        .filter(
            User.id == teacher_id,
            User.role == "teacher",
        )
        .first()
    )
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    # delete classes owned by this teacher + members + messages
    classes = db.query(Class).filter(Class.owner_id == teacher.id).all()
    for cls in classes:
        db.query(ClassMember).filter(ClassMember.class_id == cls.id).delete()
        db.query(Message).filter(Message.class_id == cls.id).delete()
        db.delete(cls)

    # delete memberships where teacher is in other classes
    db.query(ClassMember).filter(ClassMember.user_id == teacher.id).delete()

    db.delete(teacher)
    db.commit()
    return {"message": "Teacher deleted"}


@app.get("/admin/students", response_model=List[StudentOut])
def list_students(db: Session = Depends(get_db)):
    students = (
        db.query(User)
        .filter(User.role == "student")
        .order_by(User.full_name)
        .all()
    )
    return students


@app.delete("/admin/students/{student_id}")
def delete_student(student_id: int, db: Session = Depends(get_db)):
    stu = (
        db.query(User)
        .filter(
            User.id == student_id,
            User.role == "student",
        )
        .first()
    )

    if not stu:
        raise HTTPException(status_code=404, detail="Student not found")

    db.query(ClassMember).filter(ClassMember.user_id == stu.id).delete()
    db.delete(stu)
    db.commit()
    return {"message": "Student deleted"}


# ====================================================
# Teacher auth
# ====================================================
@app.post("/auth/login/teacher", response_model=TeacherLoginResponse)
def login_teacher(data: TeacherLoginRequest, db: Session = Depends(get_db)):
    sid = data.staff_id.strip()

    user = (
        db.query(User)
        .filter(
            User.staff_id == sid,
            User.role == "teacher",
        )
        .first()
    )

    if not user or user.password != data.password:
        raise HTTPException(status_code=401, detail="Invalid user ID or password")

    return TeacherLoginResponse(
        token="demo-token",
        role=user.role,
        full_name=user.full_name,
        email=user.email,
        staff_id=user.staff_id or "",
    )


# ====================================================
# User profile (view + avatar upload)
# ====================================================
@app.get("/profile", response_model=UserProfile)
def get_profile(email: EmailStr, db: Session = Depends(get_db)):
    """
    Get profile info by email (for student, teacher, or admin).
    """
    e = email.strip().lower()
    user = db.query(User).filter(User.email == e).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.post("/profile/avatar", response_model=UserProfile)
async def upload_avatar(
    email: EmailStr = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload/update profile picture.
    Saves file under /uploads/avatars and stores URL in users.avatar_url.
    """
    e = email.strip().lower()
    user = db.query(User).filter(User.email == e).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    original_name = file.filename or "avatar"
    ext = os.path.splitext(original_name)[1] or ".png"
    new_name = f"{uuid4().hex}{ext}"

    disk_path = os.path.join(AVATAR_DIR, new_name)
    contents = await file.read()
    with open(disk_path, "wb") as f:
        f.write(contents)

    url_path = f"/uploads/avatars/{new_name}"
    user.avatar_url = url_path
    db.commit()
    db.refresh(user)

    return user


# ====================================================
# Classes & membership
# ====================================================
@app.post("/teacher/classes", response_model=ClassOut)
def create_class(data: CreateClassRequest, db: Session = Depends(get_db)):
    owner_email = data.owner_email.strip().lower()
    owner = (
        db.query(User)
        .filter(
            User.email == owner_email,
            User.role == "teacher",
        )
        .first()
    )

    if not owner:
        raise HTTPException(status_code=400, detail="Teacher not found")

    exists_code = db.query(Class).filter(Class.code == data.code).first()
    if exists_code:
        raise HTTPException(status_code=400, detail="Join code already used")

    cls = Class(
        name=data.name.strip(),
        semester=(data.semester or "").strip() or None,
        description=(data.description or "").strip() or None,
        code=data.code.strip().upper(),
        owner_id=owner.id,
    )

    db.add(cls)
    db.commit()
    db.refresh(cls)

    mem = ClassMember(
        class_id=cls.id,
        user_id=owner.id,
        role="teacher",
        status="active",
    )
    db.add(mem)
    db.commit()

    return cls


@app.get("/teacher/classes", response_model=List[ClassOut])
def list_teacher_classes(owner_email: EmailStr, db: Session = Depends(get_db)):
    email = owner_email.strip().lower()
    teacher = (
        db.query(User)
        .filter(
            User.email == email,
            User.role == "teacher",
        )
        .first()
    )

    if not teacher:
        raise HTTPException(status_code=400, detail="Teacher not found")

    classes = db.query(Class).filter(Class.owner_id == teacher.id).all()
    return classes


@app.post("/teacher/remove-class")
def remove_class(data: RemoveClassRequest, db: Session = Depends(get_db)):
    owner_email = data.owner_email.strip().lower()
    teacher = (
        db.query(User)
        .filter(User.email == owner_email, User.role == "teacher")
        .first()
    )
    if not teacher:
        raise HTTPException(status_code=400, detail="Teacher not found")

    cls = (
        db.query(Class)
        .filter(Class.id == data.class_id, Class.owner_id == teacher.id)
        .first()
    )
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")

    db.query(Message).filter(Message.class_id == cls.id).delete()
    db.query(ClassMember).filter(ClassMember.class_id == cls.id).delete()
    db.delete(cls)
    db.commit()
    return {"message": "Class deleted"}


@app.post("/student/join")
def student_join_class(data: JoinClassRequest, db: Session = Depends(get_db)):
    email = data.student_email.strip().lower()

    student = (
        db.query(User)
        .filter(
            User.email == email,
            User.role == "student",
        )
        .first()
    )

    if not student:
        raise HTTPException(status_code=400, detail="Student not found")

    cls = db.query(Class).filter(Class.code == data.code.strip().upper()).first()
    if not cls:
        raise HTTPException(status_code=404, detail="Join code not found")

    existing = (
        db.query(ClassMember)
        .filter(
            ClassMember.class_id == cls.id,
            ClassMember.user_id == student.id,
        )
        .first()
    )

    if existing:
        if existing.status == "active":
            return {"message": "Already a member"}
        if existing.status == "pending":
            return {"message": "Request already pending"}
        existing.status = "pending"
        db.commit()
        return {"message": "Request re-sent"}

    membership = ClassMember(
        class_id=cls.id,
        user_id=student.id,
        role="student",
        status="pending",
    )
    db.add(membership)
    db.commit()

    return {"message": "Join request sent"}


@app.get("/student/classes", response_model=List[ClassOut])
def list_student_classes(student_email: EmailStr, db: Session = Depends(get_db)):
    email = student_email.strip().lower()

    student = (
        db.query(User)
        .filter(
            User.email == email,
            User.role == "student",
        )
        .first()
    )

    if not student:
        raise HTTPException(status_code=400, detail="Student not found")

    memberships = (
        db.query(ClassMember)
        .filter(
            ClassMember.user_id == student.id,
            ClassMember.status == "active",
        )
        .all()
    )

    class_ids = [m.class_id for m in memberships]
    if not class_ids:
        return []

    classes = db.query(Class).filter(Class.id.in_(class_ids)).all()
    return classes


@app.post("/teacher/approve")
def teacher_approve(data: ApproveRequest, db: Session = Depends(get_db)):
    email = data.student_email.strip().lower()

    student = (
        db.query(User)
        .filter(
            User.email == email,
            User.role == "student",
        )
        .first()
    )

    if not student:
        raise HTTPException(status_code=400, detail="Student not found")

    m = (
        db.query(ClassMember)
        .filter(
            ClassMember.class_id == data.class_id,
            ClassMember.user_id == student.id,
        )
        .first()
    )

    if not m:
        raise HTTPException(status_code=404, detail="Membership not found")

    m.status = "active"
    db.commit()

    return {"message": "Student approved"}


@app.get("/classes/{class_id}/members", response_model=List[MemberOut])
def get_class_members(class_id: int, db: Session = Depends(get_db)):
    rows = db.query(ClassMember).filter(ClassMember.class_id == class_id).all()

    out: List[MemberOut] = []
    for m in rows:
        u = db.query(User).filter(User.id == m.user_id).first()
        email = u.email if u else ""
        out.append(
            MemberOut(
                email=email,
                role=m.role,
                status=m.status,
            )
        )
    return out


# ====================================================
# File upload for attachments
# ====================================================
@app.post("/upload")
async def upload_files(
    class_id: int = Form(...),
    files: List[UploadFile] = File(...),
):
    """
    Save files into /uploads and return metadata list:
    [{filename, url, content_type}, ...]
    """
    saved: List[AttachmentMeta] = []

    for uf in files:
        original = uf.filename or "file"
        ext = os.path.splitext(original)[1]
        new_name = f"{uuid4().hex}{ext}"
        disk_path = os.path.join(UPLOAD_DIR, new_name)

        contents = await uf.read()
        with open(disk_path, "wb") as f:
            f.write(contents)

        url_path = f"/uploads/{new_name}"

        saved.append(
            AttachmentMeta(
                filename=original,
                url=url_path,
                content_type=uf.content_type or "",
            )
        )

    return {"files": saved}


# ====================================================
# Messages for chat.html (with attachments)
# ====================================================
def message_to_out(msg: Message) -> MessageOut:
    try:
        attachments_data = json.loads(msg.attachments_json or "[]")
    except Exception:
        attachments_data = []

    attachments: List[AttachmentMeta] = []
    for a in attachments_data:
        if not isinstance(a, dict):
            continue
        attachments.append(
            AttachmentMeta(
                filename=a.get("filename", ""),
                url=a.get("url", ""),
                content_type=a.get("content_type", ""),
            )
        )

    return MessageOut(
        id=msg.id,
        class_id=msg.class_id,
        channel=msg.channel,
        sender_email=msg.sender_email,
        sender_name=msg.sender_name,
        content=msg.content,
        timestamp=msg.timestamp,
        attachments=attachments,
    )


@app.get(
    "/classes/{class_id}/messages",
    response_model=List[MessageOut],
)
def get_class_messages(
    class_id: int,
    channel: str = "general",
    db: Session = Depends(get_db),
):
    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")

    msgs = (
        db.query(Message)
        .filter(
            Message.class_id == class_id,
            Message.channel == channel,
        )
        .order_by(Message.timestamp.asc(), Message.id.asc())
        .all()
    )
    return [message_to_out(m) for m in msgs]


@app.post(
    "/classes/{class_id}/messages",
    response_model=MessageOut,
)
def post_class_message(
    class_id: int,
    data: MessageCreate,
    db: Session = Depends(get_db),
):
    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")

    attachments_json = json.dumps([a.dict() for a in data.attachments])

    msg = Message(
        class_id=class_id,
        channel=data.channel,
        sender_email=data.sender_email,
        sender_name=data.sender_name,
        content=data.content,
        attachments_json=attachments_json,
    )

    db.add(msg)
    db.commit()
    db.refresh(msg)
    return message_to_out(msg)


@app.delete("/classes/{class_id}/messages/{message_id}")
def delete_message(
    class_id: int,
    message_id: int,
    teacher_email: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Delete a single message in a class.
    Only allowed for the teacher who owns the class.
    Called like:
      DELETE /classes/{class_id}/messages/{message_id}?teacher_email=...
    """
    if not teacher_email:
        raise HTTPException(status_code=400, detail="teacher_email is required")

    email = teacher_email.strip().lower()

    # 1) Find teacher
    teacher = (
        db.query(User)
        .filter(
            User.email == email,
            User.role == "teacher",
        )
        .first()
    )
    if not teacher:
        raise HTTPException(status_code=403, detail="Teacher not found")

    # 2) Ensure class belongs to this teacher
    cls = (
        db.query(Class)
        .filter(
            Class.id == class_id,
            Class.owner_id == teacher.id,
        )
        .first()
    )
    if not cls:
        raise HTTPException(status_code=403, detail="You are not the owner of this class")

    # 3) Find message
    msg = (
        db.query(Message)
        .filter(
            Message.id == message_id,
            Message.class_id == class_id,
        )
        .first()
    )
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    # 4) Delete
    db.delete(msg)
    db.commit()
    return {"message": "Message deleted"}
