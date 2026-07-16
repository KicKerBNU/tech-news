const { json, resendHeaders, verifyEmailSignature } = require('./_lib/newsletter')

exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') {
    return json(204, {})
  }

  if (event.httpMethod !== 'POST') {
    return json(405, { error: 'Method not allowed' })
  }

  const apiKey = process.env.RESEND_API_KEY
  const secret = process.env.UNSUBSCRIBE_SECRET
  if (!apiKey || !secret) {
    return json(503, { error: 'Newsletter is not configured yet' })
  }

  let email
  let signature
  try {
    const body = JSON.parse(event.body || '{}')
    email = body.email?.trim().toLowerCase()
    signature = body.sig?.trim()
  } catch {
    return json(400, { error: 'Invalid request body' })
  }

  if (!email || !verifyEmailSignature(email, signature, secret)) {
    return json(400, { error: 'Invalid or expired unsubscribe link' })
  }

  const patch = await fetch(`https://api.resend.com/contacts/${encodeURIComponent(email)}`, {
    method: 'PATCH',
    headers: resendHeaders(apiKey),
    body: JSON.stringify({ unsubscribed: true }),
  })

  if (patch.ok) {
    return json(200, { message: 'You have been unsubscribed.' })
  }

  const body = await patch.text()
  console.error('Resend unsubscribe failed', body)

  if (patch.status === 404) {
    return json(404, { error: 'Subscriber not found' })
  }

  return json(500, { error: 'Could not process unsubscribe' })
}
