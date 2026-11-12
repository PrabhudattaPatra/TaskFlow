import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { Button, Field } from '../components/ui'
import { useAction } from '../hooks'

function AuthForm({ mode }) {
  const { login, signup } = useAuth()
  const nav = useNavigate()
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [errors, setErrors] = useState({})
  const isSignup = mode === 'signup'
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const [submit, busy] = useAction(async (e) => {
    e.preventDefault()
    setErrors({})
    const local = {}
    if (isSignup && !form.name.trim()) local.name = 'Name is required'
    if (!/^\S+@\S+\.\S+$/.test(form.email)) local.email = 'Enter a valid email address'
    if (isSignup) {
      if (form.password.length < 8) local.password = 'Password must be at least 8 characters'
      else if (!/[A-Za-z]/.test(form.password) || !/\d/.test(form.password)) local.password = 'Password must contain a letter and a number'
    } else if (!form.password) local.password = 'Password is required'
    if (Object.keys(local).length) return setErrors(local)
    try {
      if (isSignup) await signup(form.name, form.email, form.password)
      else await login(form.email, form.password)
      nav('/')
    } catch (err) {
      setErrors(Object.keys(err.fieldErrors || {}).length ? err.fieldErrors : { form: err.message })
    }
  })

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={submit} noValidate>
        <h1>TaskFlow</h1>
        <p className="muted">{isSignup ? 'Create your account' : 'Sign in to continue'}</p>
        {errors.form && <div className="banner error" role="alert">{errors.form}</div>}
        {isSignup && <Field label="Name" error={errors.name}><input value={form.name} onChange={set('name')} autoFocus /></Field>}
        <Field label="Email" error={errors.email}><input type="email" value={form.email} onChange={set('email')} autoFocus={!isSignup} /></Field>
        <Field label="Password" error={errors.password}>
          <input type="password" value={form.password} onChange={set('password')} />
        </Field>
        {isSignup && <p className="hint">At least 8 characters, with a letter and a number.</p>}
        <Button className="primary block" busy={busy} busyLabel={isSignup ? 'Creating…' : 'Signing in…'}>
          {isSignup ? 'Sign up' : 'Log in'}
        </Button>
        <p className="muted center">
          {isSignup ? <>Have an account? <Link to="/login">Log in</Link></> : <>New here? <Link to="/signup">Sign up</Link></>}
        </p>
      </form>
    </div>
  )
}

export const LoginPage = () => <AuthForm mode="login" />
export const SignupPage = () => <AuthForm mode="signup" />
