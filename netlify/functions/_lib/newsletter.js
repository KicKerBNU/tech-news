const crypto = require('crypto')

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function json(statusCode, body) {
  return {
    statusCode,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*',
    },
    body: JSON.stringify(body),
  }
}

function resendHeaders(apiKey) {
  return {
    Authorization: `Bearer ${apiKey}`,
    'Content-Type': 'application/json',
  }
}

function signEmail(email, secret) {
  return crypto.createHmac('sha256', secret).update(email).digest('base64url')
}

function verifyEmailSignature(email, signature, secret) {
  if (!signature) return false
  const expected = signEmail(email, secret)
  try {
    return crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expected))
  } catch {
    return false
  }
}

module.exports = {
  EMAIL_RE,
  json,
  resendHeaders,
  signEmail,
  verifyEmailSignature,
}
