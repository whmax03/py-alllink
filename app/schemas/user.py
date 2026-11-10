from pydantic import BaseModel, EmailStr, field_validator


class UserBase(BaseModel):
    name: str
    email: EmailStr


class UserCreate(UserBase):
    pass


class UserResponse(UserBase):
    id: int

    class Config:
        from_attributes = True


# ---------- 认证相关 Schema ----------

class UserRegister(BaseModel):
    """注册请求"""
    name: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError("密码长度不能少于 6 位")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("密码过长，请控制在 72 字节以内（中文约 24 个字）")
        return v


class UserLogin(BaseModel):
    """登录请求"""
    email: EmailStr
    password: str


class ChangePassword(BaseModel):
    """修改密码请求"""
    email: EmailStr
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v):
        if len(v) < 6:
            raise ValueError("新密码长度不能少于 6 位")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("新密码过长，请控制在 72 字节以内（中文约 24 个字）")
        return v


class TokenResponse(BaseModel):
    """登录成功返回的 token 信息"""
    access_token: str
    token_type: str = "bearer"
