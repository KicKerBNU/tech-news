const { EMAIL_RE, json, resendHeaders } = require('./_lib/newsletter')

exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') {
    return json(204, {})
  }

  if (event.httpMethod !== 'POST') {
    return json(405, { error: 'Method not allowed' })
  }

  const apiKey = process.env.RESEND_API_KEY
  if (!apiKey) {
    return json(503, { error: 'Newsletter is not configured yet' })
  }

  let email
  try {
    email = JSON.parse(event.body || '{}').email?.trim().toLowerCase()
  } catch {
    return json(400, { error: 'Invalid request body' })
  }

  if (!email || !EMAIL_RE.test(email)) {
    return json(400, { error: 'Enter a valid email address' })
  }

  const create = await fetch('https://api.resend.com/contacts', {
    method: 'POST',
    headers: resendHeaders(apiKey),
    body: JSON.stringify({ email, unsubscribed: false }),
  })

  if (create.ok) {
    return json(201, { message: 'Subscribed — check your inbox after the next daily digest.' })
  }

  const createBody = await create.text()
  let createError
  try {
    createError = JSON.parse(createBody)
  } catch {
    createError = { message: createBody }
  }

  if (create.status === 401 && String(createError.message || '').includes('restricted')) {
    return json(503, {
      error:
        'Newsletter API key needs Full access in Resend (not send-only). Create a new key at resend.com/api-keys.',
    })
  }

  // Contact already exists — reactivate if they previously unsubscribed
  if (create.status === 409 || createBody.toLowerCase().includes('already')) {
    const reactivate = await fetch(`https://api.resend.com/contacts/${encodeURIComponent(email)}`, {
      method: 'PATCH',
      headers: resendHeaders(apiKey),
      body: JSON.stringify({ unsubscribed: false }),
    })

    if (reactivate.ok) {
      return json(200, { message: 'Welcome back — you are subscribed again.' })
    }

    if (reactivate.status === 404) {
      return json(500, { error: 'Could not process subscription' })
    }

    const patchBody = await reactivate.text()
    console.error('Resend reactivate failed', patchBody)

    if (reactivate.status === 200 || patchBody.includes('unsubscribed')) {
      return json(200, { message: 'You are already subscribed.' })
    }

    return json(500, { error: 'Could not process subscription' })
  }

  console.error('Resend create contact failed', createBody)
  return json(500, { error: 'Could not process subscription' })
}
